"""
LogsSAJ — Launcher com auto-atualização e splash screen.
Compilar com: build.bat
"""
import os
import sys
import shutil
import subprocess
import threading
import time
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox

# Diretório base: ao lado do .exe em produção, ou pasta do script em dev
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, BASE_DIR)


# ── Localizar Python do sistema ────────────────────────────────────────────
def _find_python() -> str | None:
    for candidate in ["python", "python3"]:
        found = shutil.which(candidate)
        if found:
            return found

    # Caminhos comuns no Windows
    for ver in ("312", "311", "310", "313"):
        paths = [
            rf"C:\Python{ver}\python.exe",
            os.path.expanduser(rf"~\AppData\Local\Programs\Python\Python{ver}\python.exe"),
        ]
        for p in paths:
            if os.path.isfile(p):
                return p
    return None


# ── Splash screen ──────────────────────────────────────────────────────────
class Splash(tk.Tk):
    COR_BG     = "#0f1117"
    COR_TITULO = "#e2e8f0"
    COR_SUB    = "#64748b"
    COR_STATUS = "#94a3b8"
    COR_BAR    = "#3b82f6"

    def __init__(self):
        super().__init__()
        self.title("Logs Integração SAJ")
        self.overrideredirect(True)      # sem barra de título do OS
        self.configure(bg=self.COR_BG)
        self.attributes("-topmost", True)

        W, H = 460, 180
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")

        # Borda sutil
        self.configure(highlightbackground="#2e3250", highlightthickness=1)

        tk.Label(self, text="📋  Logs Integração SAJ",
                 font=("Segoe UI", 15, "bold"),
                 bg=self.COR_BG, fg=self.COR_TITULO).pack(pady=(28, 4))

        tk.Label(self, text="logexternalizer · SAJ / Softplan",
                 font=("Segoe UI", 9),
                 bg=self.COR_BG, fg=self.COR_SUB).pack()

        self._status_var = tk.StringVar(value="Iniciando...")
        tk.Label(self, textvariable=self._status_var,
                 font=("Segoe UI", 9),
                 bg=self.COR_BG, fg=self.COR_STATUS).pack(pady=(14, 6))

        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("Blue.Horizontal.TProgressbar",
                        troughcolor="#1e2130", background=self.COR_BAR,
                        thickness=6)
        self._bar = ttk.Progressbar(self, mode="indeterminate", length=400,
                                    style="Blue.Horizontal.TProgressbar")
        self._bar.pack()
        self._bar.start(12)

    def set_status(self, msg: str):
        self._status_var.set(msg)
        self.update()

    def fechar(self):
        try:
            self._bar.stop()
            self.destroy()
        except Exception:
            pass


# ── Fluxo principal ────────────────────────────────────────────────────────
def _run(splash: Splash):

    # 1. Verificar e aplicar atualização
    splash.set_status("Verificando atualizações...")
    atualizado = False
    try:
        from atualizador import verificar_e_atualizar
        atualizado = verificar_e_atualizar(BASE_DIR, splash.set_status)
    except Exception:
        pass

    if atualizado:
        splash.set_status("Atualização aplicada! Reiniciando...")
        time.sleep(1.5)
        splash.fechar()
        exe = sys.executable
        os.execv(exe, [exe] + sys.argv)
        return

    # 2. Localizar Python
    splash.set_status("Localizando Python instalado...")
    python = _find_python()
    if not python:
        splash.fechar()
        messagebox.showerror(
            "Python não encontrado",
            "O Python não foi encontrado neste computador.\n\n"
            "Acesse https://www.python.org/downloads/ , baixe e instale.\n"
            "Durante a instalação marque: ✔ Add Python to PATH\n\n"
            "Após instalar, abra o sistema novamente."
        )
        return

    # 3. Instalar / verificar dependências
    req = os.path.join(BASE_DIR, "requirements.txt")
    if os.path.exists(req):
        splash.set_status("Verificando dependências (pode demorar na 1ª vez)...")
        subprocess.run(
            [python, "-m", "pip", "install", "-r", req,
             "--quiet", "--disable-pip-version-check"],
            capture_output=True,
        )

    # 4. Abrir o navegador 4s depois de iniciar o Streamlit
    def _open_browser():
        time.sleep(4)
        webbrowser.open("http://localhost:8501")

    threading.Thread(target=_open_browser, daemon=True).start()

    # 5. Fechar splash e iniciar Streamlit
    splash.set_status("Abrindo no navegador...")
    time.sleep(0.6)
    splash.fechar()

    app_py = os.path.join(BASE_DIR, "app.py")
    subprocess.run([
        python, "-m", "streamlit", "run", app_py,
        "--server.port", "8501",
        "--server.headless", "false",
        "--browser.gatherUsageStats", "false",
        "--browser.serverAddress", "localhost",
    ])


def main():
    splash = Splash()
    # Roda o fluxo numa thread para não travar o loop Tk
    t = threading.Thread(target=_run, args=(splash,), daemon=True)
    t.start()
    splash.mainloop()


if __name__ == "__main__":
    main()
