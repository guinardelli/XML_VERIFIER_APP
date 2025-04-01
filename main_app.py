# main_app.py

import os
import csv
import threading
from tkinter import *
from tkinter import filedialog, messagebox, ttk
from typing import List, Tuple

# --- Importações dos módulos locais ---
from .constants import DEFAULT_ENCODING # Apenas o necessário aqui
from .verification import run_verification_checks
from .correction_structural import start_structural_correction
from .correction_value import start_manual_value_correction
from .comparison import show_comparison_window

class XMLVerifier:
    def __init__(self, root):
        self.root = root
        self.root.title("Verificador e Corretor de Arquivos XML Tekla")
        self.root.geometry("1100x700")

        # Variáveis de estado
        self.file_paths: List[str] = []
        self.results: List[Tuple[str, str, str, str]] = [] # (filename, type, description, location)
        self.is_verifying = False
        self.is_fixing = False # Para correção estrutural
        self.is_correcting_value = False # Para correção manual de valor

        # --- Configuração da UI (Widgets) ---
        self._setup_ui()

    def _setup_ui(self):
        """Configura os widgets da interface gráfica."""
        main_frame = Frame(self.root)
        main_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)

        # --- Frame de Seleção ---
        file_frame = LabelFrame(main_frame, text="Seleção de Arquivos")
        file_frame.pack(fill=X, padx=5, pady=5)
        Button(file_frame, text="Selecionar Arquivos", command=self.browse_files).grid(row=0, column=0, padx=5, pady=5)
        Button(file_frame, text="Selecionar Pasta", command=self.browse_directory).grid(row=0, column=1, padx=5, pady=5)
        Button(file_frame, text="Limpar Seleção", command=self.clear_selection).grid(row=0, column=2, padx=5, pady=5)
        self.verify_button = Button(file_frame, text="Verificar", command=self.start_verification_ui, bg="#4CAF50", fg="white")
        self.verify_button.grid(row=0, column=3, padx=5, pady=5)
        self.fix_button = Button(file_frame, text="Corrigir Estrutura", command=self.start_fixing_ui, bg="#FFA500", fg="white")
        self.fix_button.grid(row=0, column=4, padx=5, pady=5)
        self.file_label = Label(file_frame, text="Nenhum arquivo selecionado")
        self.file_label.grid(row=1, column=0, columnspan=5, padx=5, pady=5, sticky=W)

        # --- Barra de Progresso ---
        self.progress_var = DoubleVar()
        self.progress_frame = Frame(main_frame)
        self.progress_bar = ttk.Progressbar(self.progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=X, padx=5, pady=5)
        self.progress_frame.pack_forget()

        # --- Frame de Filtros ---
        filter_frame = LabelFrame(main_frame, text="Filtros")
        filter_frame.pack(fill=X, padx=5, pady=5)
        Label(filter_frame, text="Tipo:").grid(row=0, column=0, padx=5, pady=5)
        self.tipo_var = StringVar(value="Todos")
        tipo_combo = ttk.Combobox(filter_frame, textvariable=self.tipo_var, values=["Todos", "Erro", "Aviso", "Info"])
        tipo_combo.grid(row=0, column=1, padx=5, pady=5)
        tipo_combo.bind("<<ComboboxSelected>>", self.apply_filters)
        Label(filter_frame, text="Arquivo:").grid(row=0, column=2, padx=5, pady=5)
        self.arquivo_var = StringVar(value="Todos")
        self.arquivo_combo = ttk.Combobox(filter_frame, textvariable=self.arquivo_var, values=["Todos"])
        self.arquivo_combo.grid(row=0, column=3, padx=5, pady=5)
        self.arquivo_combo.bind("<<ComboboxSelected>>", self.apply_filters)
        Label(filter_frame, text="Pesquisar:").grid(row=0, column=4, padx=5, pady=5)
        self.search_var = StringVar()
        search_entry = Entry(filter_frame, textvariable=self.search_var, width=30)
        search_entry.grid(row=0, column=5, padx=5, pady=5)
        search_entry.bind("<KeyRelease>", self.apply_filters)
        Button(filter_frame, text="Aplicar Filtros", command=self.apply_filters).grid(row=0, column=6, padx=5, pady=5)
        Button(filter_frame, text="Limpar Filtros", command=self.clear_filters).grid(row=0, column=7, padx=5, pady=5)

        # --- Frame de Resultados (Treeview) ---
        result_frame = LabelFrame(main_frame, text="Resultados da Verificação")
        result_frame.pack(fill=BOTH, expand=True, padx=5, pady=5)
        self.result_tree = ttk.Treeview(result_frame, columns=("Arquivo", "Tipo", "Descrição", "Localização"),
                                        show="headings", selectmode='extended')
        self.result_tree.heading("Arquivo", text="Arquivo")
        self.result_tree.heading("Tipo", text="Tipo")
        self.result_tree.heading("Descrição", text="Descrição")
        self.result_tree.heading("Localização", text="Localização")
        self.result_tree.column("Arquivo", width=150, anchor=W)
        self.result_tree.column("Tipo", width=80, anchor=W)
        self.result_tree.column("Descrição", width=500, anchor=W)
        self.result_tree.column("Localização", width=250, anchor=W)
        y_scrollbar = ttk.Scrollbar(result_frame, orient=VERTICAL, command=self.result_tree.yview)
        self.result_tree.configure(yscroll=y_scrollbar.set)
        x_scrollbar = ttk.Scrollbar(result_frame, orient=HORIZONTAL, command=self.result_tree.xview)
        self.result_tree.configure(xscroll=x_scrollbar.set)
        self.result_tree.grid(row=0, column=0, sticky=(N, S, E, W))
        y_scrollbar.grid(row=0, column=1, sticky=(N, S))
        x_scrollbar.grid(row=1, column=0, sticky=(E, W))
        result_frame.grid_rowconfigure(0, weight=1)
        result_frame.grid_columnconfigure(0, weight=1)
        self.result_tree.tag_configure("erro", background="#ffcccc")
        self.result_tree.tag_configure("aviso", background="#ffffcc")
        self.result_tree.tag_configure("info", background="#ccffcc")

        # --- Frame de Correção Manual ---
        correction_frame = LabelFrame(main_frame, text="Correção Manual de Valor (para item(ns) selecionado(s))")
        correction_frame.pack(fill=X, padx=5, pady=5)
        Label(correction_frame, text="Novo Valor:").grid(row=0, column=0, padx=5, pady=5, sticky=W)
        self.correction_value_var = StringVar()
        self.correction_entry = Entry(correction_frame, textvariable=self.correction_value_var, width=40)
        self.correction_entry.grid(row=0, column=1, padx=5, pady=5, sticky=W)
        self.correct_value_button = Button(correction_frame, text="Corrigir Valor Selecionado(s)", command=self.start_value_correction_ui, bg="#4682B4", fg="white")
        self.correct_value_button.grid(row=0, column=2, padx=10, pady=5)

        # --- Frame de Botões de Ação ---
        button_frame = Frame(main_frame)
        button_frame.pack(fill=X, pady=5)
        Button(button_frame, text="Exportar Resultados", command=self.export_results).pack(side=LEFT, padx=5)
        Button(button_frame, text="Limpar Resultados", command=self.clear_results_ui).pack(side=LEFT, padx=5)
        Button(button_frame, text="Comparar Original/Corrigido", command=self.compare_files_ui).pack(side=LEFT, padx=5)
        self.count_var = StringVar(value="0")
        Label(button_frame, textvariable=self.count_var, font=("Arial", 10, "bold")).pack(side=RIGHT)
        Label(button_frame, text="Problemas exibidos: ").pack(side=RIGHT, padx=5)

        # --- Status Bar ---
        self.status_var = StringVar()
        self.status_var.set("Pronto")
        status_bar = Label(self.root, textvariable=self.status_var, bd=1, relief=SUNKEN, anchor=W)
        status_bar.pack(side=BOTTOM, fill=X)

    # --- Métodos de Interface / Ações do Usuário ---

    def browse_files(self):
        filenames = filedialog.askopenfilenames(
            title="Selecione arquivos XML",
            filetypes=(("Arquivos XML", "*.xml"), ("Todos os arquivos", "*.*")),
            parent=self.root
        )
        if filenames:
            self.file_paths = [f for f in filenames if f.lower().endswith('.xml')]
            if len(self.file_paths) != len(filenames):
                 messagebox.showwarning("Seleção", "Apenas arquivos com extensão .xml foram selecionados.", parent=self.root)
            self.update_file_label()
            self.clear_results()

    def browse_directory(self):
        directory = filedialog.askdirectory(title="Selecione uma pasta com arquivos XML", parent=self.root)
        if directory:
            self.file_paths = [os.path.join(directory, f) for f in os.listdir(directory)
                              if f.lower().endswith('.xml')]
            self.update_file_label()
            self.clear_results()

    def clear_selection(self):
        self.file_paths = []
        self.update_file_label()
        self.clear_results()

    def update_file_label(self):
        if not self.file_paths:
            self.file_label.config(text="Nenhum arquivo selecionado")
        elif len(self.file_paths) == 1:
            self.file_label.config(text=f"1 arquivo selecionado: {os.path.basename(self.file_paths[0])}")
        else:
            self.file_label.config(text=f"{len(self.file_paths)} arquivos selecionados")
        arquivos = ["Todos"] + sorted(list(set([os.path.basename(p) for p in self.file_paths])))
        self.arquivo_combo.config(values=arquivos)
        self.arquivo_var.set("Todos")

    def start_verification_ui(self):
        """Inicia a verificação a partir do botão da UI."""
        if self.is_verifying or self.is_fixing or self.is_correcting_value:
            messagebox.showwarning("Aguarde", "Outra operação já está em andamento.", parent=self.root)
            return
        if not self.file_paths:
            messagebox.showerror("Erro", "Por favor, selecione pelo menos um arquivo XML.", parent=self.root)
            return
        self.is_verifying = True
        self.disable_buttons()
        self.progress_frame.pack(fill=X, padx=5, pady=5)
        self.progress_var.set(0)
        self.clear_results() # Limpa resultados antes de verificar
        threading.Thread(target=self._verification_thread_runner, daemon=True).start()

    def start_fixing_ui(self):
        """Inicia a correção estrutural a partir do botão da UI."""
        # Chama a função do módulo correction_structural, passando a instância atual
        start_structural_correction(self)

    def start_value_correction_ui(self):
        """Inicia a correção de valor a partir do botão da UI."""
        # Chama a função do módulo correction_value, passando a instância atual
        start_manual_value_correction(self)

    def compare_files_ui(self):
        """Mostra a janela de comparação a partir do botão da UI."""
        # Chama a função do módulo comparison, passando a instância atual
        show_comparison_window(self)

    def clear_results_ui(self):
        """Limpa os resultados da UI."""
        self.clear_results()
        self.status_var.set("Resultados limpos.")


    # --- Métodos de Gerenciamento de Estado e UI ---

    def reset_ui_state(self):
        """Reseta o estado da UI após uma operação."""
        self.is_verifying = False
        self.is_fixing = False
        self.is_correcting_value = False
        self.enable_buttons()
        self.progress_frame.pack_forget()
        self.progress_var.set(0)

    def disable_buttons(self):
        """Desabilita botões durante operações."""
        self.verify_button.config(state=DISABLED)
        self.fix_button.config(state=DISABLED)
        self.correct_value_button.config(state=DISABLED)

    def enable_buttons(self):
        """Habilita botões após operações."""
        self.verify_button.config(state=NORMAL)
        self.fix_button.config(state=NORMAL)
        self.correct_value_button.config(state=NORMAL)

    def update_status(self, text):
        """Atualiza a barra de status (thread-safe)."""
        self.root.after(0, lambda t=text: self.status_var.set(t))

    def add_result(self, filename: str, type: str, description: str, location: str):
        """Adiciona um resultado à lista interna (pode ser chamado por threads)."""
        self.results.append((filename, type, description, location))

    def clear_results(self):
        """Limpa a lista interna de resultados e a Treeview."""
        self.results = []
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
        self.count_var.set("0")
        # Não reseta o status aqui necessariamente

    def apply_filters(self, event=None):
        """Aplica os filtros selecionados à Treeview."""
        for item in self.result_tree.get_children(): self.result_tree.delete(item)
        filtered_results = []
        tipo_filter = self.tipo_var.get()
        arquivo_filter = self.arquivo_var.get()
        search_filter = self.search_var.get().lower().strip()
        for result in self.results: # Usa a lista interna self.results
            arquivo, tipo, descricao, localizacao = result
            if tipo_filter != "Todos" and tipo != tipo_filter: continue
            if arquivo_filter != "Todos" and arquivo != arquivo_filter: continue
            if search_filter and search_filter not in descricao.lower() and search_filter not in localizacao.lower(): continue
            filtered_results.append(result)
        for result in filtered_results:
            arquivo, tipo, descricao, localizacao = result
            tag = tipo.lower()
            self.result_tree.insert("", END, values=(arquivo, tipo, descricao, localizacao), tags=(tag,))
        self.count_var.set(str(len(filtered_results))) # Atualiza contador para itens *exibidos*

    def clear_filters(self):
        """Limpa os filtros e reaplica."""
        self.tipo_var.set("Todos")
        self.arquivo_var.set("Todos")
        self.search_var.set("")
        self.apply_filters()

    def export_results(self):
        """Exporta os resultados internos para CSV."""
        if not self.results:
            messagebox.showinfo("Exportar", "Não há resultados para exportar.", parent=self.root)
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("Text files", "*.txt"), ("All files", "*.*")],
            title="Salvar Resultados Como",
            parent=self.root
        )
        if not file_path: return
        try:
            with open(file_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
                writer.writerow(["Arquivo", "Tipo", "Descrição", "Localização"])
                for result in self.results: # Exporta todos os resultados internos
                    writer.writerow(result)
            messagebox.showinfo("Exportar", f"Resultados exportados com sucesso para:\n{file_path}", parent=self.root)
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao exportar resultados: {str(e)}", parent=self.root)

    # --- Lógica de Thread de Verificação ---

    def _verification_thread_runner(self):
        """Executa a lógica de verificação em uma thread separada."""
        all_results = []
        try:
            total_files = len(self.file_paths)
            for i, file_path in enumerate(self.file_paths):
                if not self.is_verifying: break
                base_name = os.path.basename(file_path)
                self.update_status(f"Verificando arquivo {i+1}/{total_files}: {base_name}")
                self.progress_var.set(((i + 1) / total_files) * 100)
                try:
                    # Chama a função de verificação do módulo verification
                    file_results = run_verification_checks(file_path)
                    all_results.extend(file_results)
                except Exception as e:
                    # Adiciona erro se a própria função run_verification_checks falhar
                    all_results.append((base_name, "Erro", f"Erro inesperado ao processar arquivo: {str(e)}", "Geral"))

            # Atualiza a UI após o término (na thread principal)
            self.root.after(0, self._finalize_verification, all_results)

        except Exception as e:
             print(f"Erro na thread de verificação: {e}")
             self.root.after(0, lambda: messagebox.showerror("Erro Fatal", f"Ocorreu um erro inesperado durante a verificação:\n{e}", parent=self.root))
             self.root.after(0, self.reset_ui_state)

    def _finalize_verification(self, verification_results: List[Tuple[str, str, str, str]]):
        """Atualiza a UI após a conclusão da verificação."""
        self.results = verification_results # Atualiza a lista principal de resultados
        self.update_status("Atualizando resultados na tabela...")
        self.apply_filters() # Exibe os resultados filtrados

        if not self.results:
            self.status_var.set("Verificação concluída. Nenhum problema encontrado!")
        else:
            num_erros = sum(1 for r in self.results if r[1] == "Erro")
            num_avisos = sum(1 for r in self.results if r[1] == "Aviso")
            msg = f"Verificação concluída. {len(self.results)} problemas encontrados ({num_erros} erros, {num_avisos} avisos)."
            self.status_var.set(msg)

        self.reset_ui_state()


# --- Ponto de Entrada Principal ---
def main():
    root = Tk()
    root.resizable(True, True) # Permitir redimensionamento
    app = XMLVerifier(root)
    root.mainloop()

if __name__ == "__main__":
    # Este bloco só será executado quando main_app.py for rodado diretamente
    main()