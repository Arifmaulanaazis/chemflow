"""Satu katalog sitasi untuk CLI, API, dan UI ilmiah."""
from chemflow import __version__

REFERENCES = [
 {"id":"admetlab","title":"ADMETlab 3.0: an updated comprehensive online ADMET prediction platform enhanced with broader coverage, improved performance, API functionality and decision support","authors":"Fu L et al.","year":"2024","doi":"10.1093/nar/gkae236","usage":"Prediksi ADMETLab3 bila digunakan."},
 {"id":"sklearn","title":"Scikit-learn: Machine Learning in Python","authors":"Pedregosa F et al.","year":"2011","url":"https://www.jmlr.org/papers/v12/pedregosa11a.html","usage":"Analitik PCA dan pemrosesan statistik yang memakai scikit-learn."},
 {"id":"chemflow","title":"ChemFlow: CLI and WebUI for molecular screening","authors":"Arif Maulana Azis","year":"2026","url":"https://github.com/Arifmaulanaazis/chemflow","usage":"Perangkat lunak ChemFlow; cantumkan versi dan tanggal akses.","version":__version__},
 {"id":"vina","title":"AutoDock Vina 1.2.0: New Docking Methods, Expanded Force Field, and Python Bindings","authors":"Eberhardt J, Santos-Martins D, Tillack AF, Forli S","year":"2021","doi":"10.1021/acs.jcim.1c00203","usage":"Docking AutoDock Vina."},
 {"id":"ngl","title":"NGL viewer: web-based molecular graphics for large complexes","authors":"Rose AS, Bradley AR, Valasatava Y, Duarte JM, Prlić A, Rose PW","year":"2018","doi":"10.1093/bioinformatics/bty419","usage":"Visualisasi struktur 3D di browser."},
 {"id":"openbabel","title":"Open Babel: An open chemical toolbox","authors":"O’Boyle NM et al.","year":"2011","doi":"10.1186/1758-2946-3-33","usage":"Konversi format molekul dan preparasi OpenBabel."},
 {"id":"rdkit","title":"RDKit: Open-source cheminformatics","authors":"RDKit contributors","year":"n.d.","url":"https://www.rdkit.org/","usage":"Pemrosesan SMILES, properti, dan konformer; laporkan versi RDKit aktual."},
 {"id":"rcsb","title":"The Protein Data Bank","authors":"Berman HM et al.","year":"2000","doi":"10.1093/nar/28.1.235","usage":"Data struktur PDB; sitasi juga publikasi struktur PDB yang Anda gunakan."},
]


def references():
    ordered=sorted(REFERENCES,key=lambda r:0 if r["id"]=="chemflow" else 1)
    return [{**r,"url":r.get("url") or "https://doi.org/"+r["doi"]} for r in ordered]


def render(format="text"):
    if format=="bibtex":
        names = {
            "chemflow": "Azis, Arif Maulana",
            "admetlab": "Fu, L. and others",
            "sklearn": "Pedregosa, Fabian and others",
            "vina": "Eberhardt, Jerome and Santos-Martins, Diogo and Tillack, Andreas F. and Forli, Stefano",
            "ngl": "Rose, Alexander S. and Bradley, Anthony R. and Valasatava, Yana and Duarte, Jose M. and Prlić, Andreas and Rose, Peter W.",
            "openbabel": "O'Boyle, Noel M. and others",
            "rdkit": "{RDKit contributors}",
            "rcsb": "Berman, Helen M. and others",
        }
        entries = []
        for reference in references():
            fields = {
                "title": reference["title"],
                "author": names[reference["id"]],
                "year": reference["year"],
                "url": reference["url"],
            }
            for field in ("doi", "version"):
                if reference.get(field):
                    fields[field] = reference[field]
            body = ",\n".join(f"  {key} = {{{value}}}" for key, value in fields.items())
            entries.append("@misc{" + reference["id"] + ",\n" + body + "\n}")
        return "\n\n".join(entries)
    return "\n\n".join(r["authors"]+" ("+r["year"]+"). "+r["title"]+(" v"+r["version"] if r.get("version") else "")+".\n"+r["url"]+"\n"+r["usage"] for r in references())
