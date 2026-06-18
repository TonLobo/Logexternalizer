"""
LogsSAJ — Launcher com auto-atualização e splash screen.
Compilar com: build.bat
"""
import ctypes
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox

# ── DPI awareness (obrigatório no Windows para tkinter via PyInstaller) ────
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# ── Diretório base ─────────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, BASE_DIR)

# ── Log persistente (útil para suporte) ───────────────────────────────────
import logging
logging.basicConfig(
    filename=os.path.join(BASE_DIR, "launcher.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    encoding="utf-8",
)
log = logging.getLogger("launcher")


# ── Localizar Python instalado no sistema ─────────────────────────────────
def _find_python() -> str | None:
    for name in ("python", "python3"):
        found = shutil.which(name)
        if found:
            return found
    for ver in ("313", "312", "311", "310"):
        for template in (
            rf"C:\Python{ver}\python.exe",
            os.path.expanduser(rf"~\AppData\Local\Programs\Python\Python{ver}\python.exe"),
        ):
            if os.path.isfile(template):
                return template
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
        self._q: queue.Queue = queue.Queue()

        self.title("Logs Integracao SAJ")
        self.configure(bg=self.COR_BG)
        self.attributes("-topmost", True)
        self.resizable(False, False)

        W, H = 460, 190
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{W}x{H}+{(sw - W) // 2}+{(sh - H) // 2}")

        tk.Label(self, text="Logs Integracao SAJ",
                 font=("Segoe UI", 15, "bold"),
                 bg=self.COR_BG, fg=self.COR_TITULO).pack(pady=(26, 4))

        tk.Label(self, text="logexternalizer - SAJ / Softplan",
                 font=("Segoe UI", 9),
                 bg=self.COR_BG, fg=self.COR_SUB).pack()

        self._status_var = tk.StringVar(value="Iniciando...")
        tk.Label(self, textvariable=self._status_var,
                 font=("Segoe UI", 9),
                 bg=self.COR_BG, fg=self.COR_STATUS).pack(pady=(14, 8))

        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("Blue.Horizontal.TProgressbar",
                        troughcolor="#1e2130",
                        background=self.COR_BAR,
                        thickness=6)
        self._bar = ttk.Progressbar(self, mode="indeterminate", length=400,
                                    style="Blue.Horizontal.TProgressbar")
        self._bar.pack()
        self._bar.start(12)

        self._poll()

    def post(self, *msg):
        """Chamado pela thread de trabalho (thread-safe)."""
        self._q.put(msg)

    def _poll(self):
        """Processa mensagens da fila — roda sempre na main thread."""
        try:
            while True:
                msg = self._q.get_nowait()
                kind = msg[0]
                if kind == "status":
                    self._status_var.set(msg[1])
                elif kind == "close":
                    self._fechar()
                    return
                elif kind == "error":
                    self._fechar()
                    messagebox.showerror("Erro — LogsSAJ", msg[1])
                    return
                elif kind == "restart":
                    self._fechar()
                    os.execv(sys.executable, [sys.executable] + sys.argv)
                    return
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _fechar(self):
        try:
            self._bar.stop()
            self.destroy()
        except Exception:
            pass


# ── Trabalho em segundo plano ──────────────────────────────────────────────
def _worker(splash: Splash, cmd_holder: list):

    def status(msg: str):
        log.info(msg)
        splash.post("status", msg)

    # 1. Verificar atualização
    status("Verificando atualizacoes...")
    try:
        from atualizador import verificar_e_atualizar
        atualizado = verificar_e_atualizar(BASE_DIR, status)
    except Exception as e:
        log.warning("Erro no atualizador: %s", e)
        atualizado = False

    if atualizado:
        status("Atualizacao aplicada! Reiniciando...")
        time.sleep(1.5)
        splash.post("restart")
        return

    # 2. Localizar Python
    status("Localizando Python...")
    python = _find_python()
    if not python:
        log.error("Python nao encontrado")
        splash.post(
            "error",
            "Python nao encontrado neste computador.\n\n"
            "Acesse: https://www.python.org/downloads/\n"
            "Instale e marque: Add Python to PATH\n\n"
            "Depois abra o sistema novamente.",
        )
        return

    log.info("Python encontrado: %s", python)

    # 3. Instalar dependências
    req = os.path.join(BASE_DIR, "requirements.txt")
    if os.path.exists(req):
        status("Verificando dependencias...")
        result = subprocess.run(
            [python, "-m", "pip", "install", "-r", req,
             "--quiet", "--disable-pip-version-check"],
            capture_output=True,
        )
        log.info("pip exit code: %s", result.returncode)

    # 4. Abre navegador 4s depois de iniciar o Streamlit
    def _open_browser():
        time.sleep(4)
        webbrowser.open("http://localhost:8501")

    threading.Thread(target=_open_browser, daemon=True).start()

    # 5. Passa o comando para o main thread executar após fechar a splash
    app_py = os.path.join(BASE_DIR, "app.py")
    cmd_holder[0] = [
        python, "-m", "streamlit", "run", app_py,
        "--server.port", "8501",
        "--server.headless", "false",
        "--browser.gatherUsageStats", "false",
        "--browser.serverAddress", "localhost",
    ]
    status("Abrindo no navegador...")
    time.sleep(0.8)
    splash.post("close")


# ── Ponto de entrada ───────────────────────────────────────────────────────
def main():
    log.info("=== LogsSAJ %s iniciado (frozen=%s) ===",
             open(os.path.join(BASE_DIR, "version.txt")).read().strip()
             if os.path.exists(os.path.join(BASE_DIR, "version.txt")) else "?",
             getattr(sys, "frozen", False))
    try:
        cmd_holder: list = [None]
        splash = Splash()
        t = threading.Thread(target=_worker, args=(splash, cmd_holder), daemon=True)
        t.start()
        splash.mainloop()
        if cmd_holder[0]:
            log.info("Iniciando Streamlit...")
            subprocess.run(cmd_holder[0])
            log.info("Streamlit encerrado.")
        else:
            log.info("Nenhum comando para executar — encerrando.")
    except Exception as e:
        log.exception("ERRO FATAL: %s", e)
        try:
            messagebox.showerror("Erro — LogsSAJ", f"Erro ao iniciar:\n\n{e}")
        except Exception:
            pass


if __name__ == "__main__":
    main()
