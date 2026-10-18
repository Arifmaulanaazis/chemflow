"""Validasi balasan terstruktur sebelum melepas proses CLI ilmiah yang menunggu."""
import math
from fastapi import HTTPException


def validate_answer(prompt, answer):
    if prompt["kind"] == "smiles":
        from rdkit import Chem
        value = answer.get("smiles", "")
        if not isinstance(value, str) or len(value) > 10000:
            raise HTTPException(422, "SMILES terlalu panjang atau bukan teks.")
        value = value.strip()
        if value and Chem.MolFromSmiles(value) is None:
            raise HTTPException(422, "SMILES tidak valid. Perbaiki struktur atau pilih lewati.")
        return {"smiles": value}
    if prompt["kind"] == "gridbox":
        result = {}
        for key in ("center", "size"):
            values = answer.get(key)
            if not isinstance(values, list) or len(values) != 3 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or abs(v) >= 100000 for v in values):
                raise HTTPException(422, "Isi tiga koordinat dan tiga ukuran yang valid.")
            if key == "size" and not all(0 < v <= 200 for v in values):
                raise HTTPException(422, "Ukuran gridbox harus > 0 hingga 200 Å.")
            result[key] = values
        native = answer.get("native", "manual")
        if native != "manual" and native not in {c["label"] for c in prompt["choices"]}:
            raise HTTPException(422, "Ligan native tidak tersedia.")
        result["native"] = native
        return result
    raise HTTPException(422, "Jenis input tidak dikenal.")
