# comparison.py

import os
import difflib
from tkinter import *
from tkinter import ttk, messagebox
from typing import TYPE_CHECKING

# Importa do projeto local
from .constants import DEFAULT_ENCODING

# Evita importação circular para type hinting
if TYPE_CHECKING:
    from .main_app import XMLVerifier

# --- Funções Auxiliares de Comparação ---

def _sync_scroll(text1, text2):
    """ Retorna uma função de callback para sincronizar o scroll Y."""
    def _sync(*args):
        try: text1.yview_moveto(args[0])
        except TclError: pass
        try: text2.yview_moveto(args[0])
        except TclError: pass
    return _sync

def _sync_scroll_x(text1, text2):
    """ Retorna uma função de callback para sincronizar o scroll X."""
    def _sync(*args):
        try: text1.xview_moveto(args[0])
        except TclError: pass
        try: text2.xview_moveto(args[0])
        except TclError: pass
    return _sync

def _highlight_inline_diff(text_widget, line_num, diff_info, tag_name):
    """Aplica tag a caracteres específicos numa linha do Text widget."""
    if line_num < 1: return
    start_index = f"{line_num}.0"
    end_index = f"{line_num}.end"
    try:
        line_content = text_widget.get(start_index, end_index)
        if line_content.strip() == "": return # Ignorar linhas de placeholder
    except TclError: return

    char_index_offset = 6 # Ajuste para 'NNNN[+- ] '
    for i, marker in enumerate(diff_info.rstrip()):
         if marker in ('^', '-', '+'):
             char_pos = i + char_index_offset
             try:
                 text_widget.tag_add(tag_name, f"{line_num}.{char_pos}", f"{line_num}.{char_pos + 1}")
             except TclError: pass

# --- Função Principal de Comparação (Chamada pela UI) ---

def show_comparison_window(app_instance: 'XMLVerifier'):
    """Cria e exibe a janela de comparação de arquivos."""
    selection = app_instance.result_tree.selection()
    if not selection:
        messagebox.showinfo("Comparar Arquivos", "Selecione um resultado na tabela.", parent=app_instance.root)
        return
    if len(selection) > 1:
         messagebox.showwarning("Comparar Arquivos", "Selecione apenas UM resultado.", parent=app_instance.root)
         return

    try:
        item = app_instance.result_tree.item(selection[0])
        values = item["values"]
        if not values: return
        arquivo_base = values[0]
    except Exception:
        messagebox.showerror("Erro", "Não foi possível obter dados do item selecionado.", parent=app_instance.root)
        return

    file_path = None
    for path in app_instance.file_paths:
        if os.path.basename(path) == arquivo_base:
            file_path = path
            break

    if not file_path or not os.path.exists(file_path):
        messagebox.showerror("Erro", f"Arquivo '{arquivo_base}' não encontrado.", parent=app_instance.root)
        return

    backup_path = file_path + ".bak"
    if not os.path.exists(backup_path):
        messagebox.showinfo("Comparar Arquivos", f"Backup '{os.path.basename(backup_path)}' não encontrado.", parent=app_instance.root)
        return

    try:
        with open(backup_path, 'r', encoding=DEFAULT_ENCODING, errors='replace') as f_bak: backup_content = f_bak.readlines()
        with open(file_path, 'r', encoding=DEFAULT_ENCODING, errors='replace') as f_curr: current_content = f_curr.readlines()
    except Exception as e:
        messagebox.showerror("Erro de Leitura", f"Erro ao ler arquivos:\n{e}", parent=app_instance.root)
        return

    # --- Criação da Janela Toplevel ---
    diff_window = Toplevel(app_instance.root)
    diff_window.title(f"Comparação: {arquivo_base} (Original vs. Corrigido)")
    diff_window.geometry("1100x700")

    diff_main_frame = Frame(diff_window)
    diff_main_frame.pack(fill=BOTH, expand=True, padx=5, pady=5)

    Label(diff_main_frame, text=f"Original ({os.path.basename(backup_path)})", font=("Arial", 10, "bold")).grid(row=0, column=0, padx=5, pady=2, sticky=W)
    Label(diff_main_frame, text=f"Corrigido ({arquivo_base})", font=("Arial", 10, "bold")).grid(row=0, column=1, padx=5, pady=2, sticky=W)

    original_text = Text(diff_main_frame, wrap=NONE, font=("Courier New", 9), borderwidth=1, relief="solid")
    corrected_text = Text(diff_main_frame, wrap=NONE, font=("Courier New", 9), borderwidth=1, relief="solid")

    scroll_y = Scrollbar(diff_main_frame, orient=VERTICAL)
    scroll_x = Scrollbar(diff_main_frame, orient=HORIZONTAL)

    original_text.config(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
    corrected_text.config(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
    scroll_y.config(command=_sync_scroll(original_text, corrected_text)) # Chama helper local
    scroll_x.config(command=_sync_scroll_x(original_text, corrected_text)) # Chama helper local

    original_text.grid(row=1, column=0, sticky="nsew", padx=(5,0), pady=(0,5))
    corrected_text.grid(row=1, column=1, sticky="nsew", padx=(5,5), pady=(0,5))
    scroll_y.grid(row=1, column=2, sticky="ns", pady=(0,5))
    scroll_x.grid(row=2, column=0, columnspan=2, sticky="ew", padx=(5,0))

    diff_main_frame.grid_rowconfigure(1, weight=1)
    diff_main_frame.grid_columnconfigure(0, weight=1)
    diff_main_frame.grid_columnconfigure(1, weight=1)

    # --- Cálculo e Exibição das Diferenças ---
    diff_result = list(difflib.ndiff(backup_content, current_content))
    original_line_num = 1
    corrected_line_num = 1

    for line in diff_result:
        code = line[:2]
        text_content = line[2:]
        if code == '  ':
            original_text.insert(END, f"{original_line_num:<4d}  {text_content}")
            corrected_text.insert(END, f"{corrected_line_num:<4d}  {text_content}")
            original_line_num += 1; corrected_line_num += 1
        elif code == '- ':
            original_text.insert(END, f"{original_line_num:<4d}- {text_content}", "removed")
            corrected_text.insert(END, "\n", "placeholder")
            original_line_num += 1
        elif code == '+ ':
            original_text.insert(END, "\n", "placeholder")
            corrected_text.insert(END, f"{corrected_line_num:<4d}+ {text_content}", "added")
            corrected_line_num += 1
        elif code == '? ':
             _highlight_inline_diff(original_text, original_line_num -1, text_content, "diff_char_orig") # Chama helper local
             _highlight_inline_diff(corrected_text, corrected_line_num -1, text_content, "diff_char_corr") # Chama helper local

    # Configuração das Tags
    original_text.tag_configure("removed", background="#ffdddd", foreground="#a00000")
    corrected_text.tag_configure("added", background="#ddffdd", foreground="#006400")
    original_text.tag_configure("diff_char_orig", background="#ffcccc", underline=True)
    corrected_text.tag_configure("diff_char_corr", background="#ccffcc", underline=True)
    original_text.tag_configure("placeholder", background="#f0f0f0")
    corrected_text.tag_configure("placeholder", background="#f0f0f0")

    original_text.config(state=DISABLED)
    corrected_text.config(state=DISABLED)

    Button(diff_window, text="Fechar", command=diff_window.destroy).pack(pady=5)