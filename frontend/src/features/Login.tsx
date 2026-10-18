import BrandMark from "../components/atoms/BrandMark";
import MolecularSketch from "../components/molecules/MolecularSketch";
import { useState } from "react";
import { motion } from "motion/react";
import { ArrowRight, Eye, ShieldCheck } from "../components/atoms/Icons";
import { api, setCsrf } from "../lib/api";
import { Button, Notice } from "../components/atoms";

export default function Login({ onLogin }: { onLogin: () => void }) {
  const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <main className="login-shell">
      <section className="login-story" aria-label="ChemFlow molecular workspace">
        <div className="brand"><BrandMark />chemflow<span>3.0</span></div>
        <div className="login-copy">
          <h1>Ruang untuk<br />penemuan berikutnya.</h1>
          <p>Preparasi, docking, dan analisis molekuler.<br />Satu pipeline. Setiap hasil dapat ditelusuri.</p>
          <div className="login-visual"><MolecularSketch variant="login" /></div>
        </div>
        <span className="login-footer">ChemFlow · Molecular research workspace</span>
      </section>
      <section className="login-form" aria-labelledby="login-heading">
        <motion.div className="login-card" initial={{opacity:0,y:12}} animate={{opacity:1,y:0}} transition={{duration:.35}}>
          <div className="login-security-mark"><ShieldCheck size={26} aria-hidden="true" /></div>
          <h2 id="login-heading">Masuk ke ruang kerja</h2>
          <p className="login-intro">Lanjutkan eksperimen dengan kata sandi ruang kerja Anda.</p>
          <form aria-busy={busy} onSubmit={async e=>{
            e.preventDefault();
            if(busy) return;
            setBusy(true);setError("");
            try {
              const result=await api<{csrf:string}>("/login",{method:"POST",body:JSON.stringify({password})});
              setCsrf(result.csrf);setPassword("");onLogin();
            } catch(err) { setError((err as Error).message); }
            finally {setBusy(false);}
          }}>
            {error && <div id="login-error"><Notice>{error}</Notice></div>}
            <label htmlFor="password">Kata sandi ruang kerja</label>
            <div className="login-password">
              <input id="password" type={visible?"text":"password"} autoComplete="current-password"
                required value={password} disabled={busy} aria-invalid={!!error}
                aria-describedby={`login-password-help${error?" login-error":""}`}
                onChange={e=>setPassword(e.target.value)} />
              <button className="login-reveal" type="button" disabled={busy}
                aria-label={visible?"Sembunyikan kata sandi":"Tampilkan kata sandi"}
                aria-pressed={visible} onClick={()=>setVisible(value=>!value)}>
                <Eye size={20} aria-hidden="true" />
              </button>
            </div>
            <p id="login-password-help" className="login-help">Gunakan kata sandi dari operator atau terminal server.</p>
            <Button type="submit" disabled={busy}>{busy?"Menghubungkan…":"Masuk"}<ArrowRight size={18} aria-hidden="true" /></Button>
          </form>
          <div className="login-session-note"><ShieldCheck size={17} aria-hidden="true" /><small>Sesi berlaku 8 jam. Berkas dan perhitungan tetap tersimpan di mesin server.</small></div>
        </motion.div>
      </section>
    </main>
  );
}
