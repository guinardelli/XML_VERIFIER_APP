# file_movement.py

import os
import shutil
import threading
from tkinter import filedialog, messagebox, Toplevel, Frame, Label, Button, Listbox, Scrollbar, SINGLE, END, BOTH, LEFT, RIGHT, Y, StringVar
from typing import List, Tuple, TYPE_CHECKING, Optional

# Evita importação circular para type hinting
if TYPE_CHECKING:
    from .main_app import XMLVerifier

def show_move_files_dialog(app_instance: 'XMLVerifier'):
    """Exibe a janela de diálogo para mover os arquivos selecionados."""
    if app_instance.is_verifying or app_instance.is_fixing or app_instance.is_correcting_value:
        messagebox.showwarning("Aguarde", "Outra operação já está em andamento.", parent=app_instance.root)
        return
    
    selected_items = app_instance.result_tree.selection()
    if not selected_items:
        selected_files = app_instance.file_paths.copy() if app_instance.file_paths else []
        if not selected_files:
            messagebox.showinfo("Mover Arquivos", "Selecione pelo menos um resultado ou carregue arquivos para mover.", parent=app_instance.root)
            return
    else:
        # Extrai nomes de arquivos únicos dos itens selecionados
        unique_files = set()
        for item_id in selected_items:
            try:
                item_values = app_instance.result_tree.item(item_id, "values")
                if item_values:
                    file_name = item_values[0]  # O nome do arquivo é o primeiro valor
                    unique_files.add(file_name)
            except Exception:
                continue
        
        # Mapeia nomes de arquivo para caminhos completos
        selected_files = []
        for file_name in unique_files:
            for path in app_instance.file_paths:
                if os.path.basename(path) == file_name:
                    selected_files.append(path)
                    break
    
    if not selected_files:
        messagebox.showinfo("Mover Arquivos", "Nenhum arquivo válido selecionado para mover.", parent=app_instance.root)
        return
    
    # Cria a janela de diálogo para mover arquivos
    move_dialog = Toplevel(app_instance.root)
    move_dialog.title("Mover Arquivos")
    move_dialog.geometry("600x500")
    move_dialog.transient(app_instance.root)
    move_dialog.grab_set()
    
    # Status
    status_var = StringVar()
    status_var.set(f"{len(selected_files)} arquivo(s) selecionado(s) para mover")
    
    # Frame principal
    main_frame = Frame(move_dialog)
    main_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)
    
    # Lista de arquivos
    list_frame = Frame(main_frame)
    list_frame.pack(fill=BOTH, expand=True, pady=5)
    
    Label(list_frame, text="Arquivos a serem movidos:").pack(anchor='w')
    
    list_subframe = Frame(list_frame)
    list_subframe.pack(fill=BOTH, expand=True)
    
    scrollbar = Scrollbar(list_subframe)
    scrollbar.pack(side=RIGHT, fill=Y)
    
    file_listbox = Listbox(list_subframe, selectmode=SINGLE, width=70, height=15)
    file_listbox.pack(side=LEFT, fill=BOTH, expand=True)
    file_listbox.config(yscrollcommand=scrollbar.set)
    scrollbar.config(command=file_listbox.yview)
    
    for file in selected_files:
        file_listbox.insert(END, file)
    
    # Botões de ação
    button_frame = Frame(main_frame)
    button_frame.pack(fill='x', pady=10)
    
    def select_destination():
        dest_dir = filedialog.askdirectory(
            title="Selecionar Pasta de Destino",
            parent=move_dialog
        )
        if dest_dir:
            status_var.set(f"Destino: {dest_dir}")
            move_files(selected_files, dest_dir, move_dialog, app_instance, status_var)
    
    Button(button_frame, text="Selecionar Destino e Mover", command=select_destination, 
           bg="#4CAF50", fg="white", pady=5).pack(side=LEFT, padx=5)
    Button(button_frame, text="Cancelar", command=move_dialog.destroy, 
           bg="#f44336", fg="white", pady=5).pack(side=LEFT, padx=5)
    
    # Barra de status
    status_label = Label(move_dialog, textvariable=status_var, bd=1, relief='sunken', anchor='w')
    status_label.pack(side='bottom', fill='x')

def move_files(files: List[str], destination: str, dialog: Toplevel, 
               app_instance: 'XMLVerifier', status_var: StringVar):
    """Inicia uma thread para mover os arquivos para o destino selecionado."""
    if not os.path.exists(destination):
        messagebox.showerror("Erro", f"Pasta de destino não existe: {destination}", parent=dialog)
        return
    
    # Confirmação final
    if not messagebox.askyesno("Confirmar", 
                               f"Mover {len(files)} arquivo(s) para:\n{destination}?", 
                               parent=dialog):
        return
    
    # Desativa botões durante a operação
    for widget in dialog.winfo_children():
        if isinstance(widget, Button):
            widget.config(state='disabled')
    
    status_var.set("Movendo arquivos...")
    
    # Inicia thread para mover arquivos
    threading.Thread(
        target=move_files_thread,
        args=(files, destination, dialog, app_instance, status_var),
        daemon=True
    ).start()

def move_files_thread(files: List[str], destination: str, dialog: Toplevel, 
                      app_instance: 'XMLVerifier', status_var: StringVar):
    """Thread para mover os arquivos selecionados para o destino."""
    results = {"success": [], "failed": []}
    
    for file_path in files:
        try:
            file_name = os.path.basename(file_path)
            dest_path = os.path.join(destination, file_name)
            
            # Verifica se o arquivo já existe no destino
            if os.path.exists(dest_path):
                # Se já existe, adiciona número sequencial
                base, ext = os.path.splitext(file_name)
                counter = 1
                while os.path.exists(dest_path):
                    new_name = f"{base}_{counter}{ext}"
                    dest_path = os.path.join(destination, new_name)
                    counter += 1
            
            # Move o arquivo
            shutil.move(file_path, dest_path)
            results["success"].append((file_path, dest_path))
        except Exception as e:
            results["failed"].append((file_path, str(e)))
    
    # Atualiza UI na thread principal
    dialog.after(0, lambda: finalize_move_operation(results, dialog, app_instance, status_var))

def finalize_move_operation(results: dict, dialog: Toplevel, 
                            app_instance: 'XMLVerifier', status_var: StringVar):
    """Finaliza a operação de movimentação na thread principal."""
    success_count = len(results["success"])
    failed_count = len(results["failed"])
    
    # Atualiza status
    if failed_count == 0:
        status_var.set(f"{success_count} arquivo(s) movido(s) com sucesso.")
        messagebox.showinfo("Concluído", 
                           f"{success_count} arquivo(s) movido(s) com sucesso.", 
                           parent=dialog)
        dialog.after(1000, dialog.destroy)  # Fecha o diálogo após 1 segundo
    else:
        status_var.set(f"{success_count} sucesso(s), {failed_count} falha(s).")
        error_msg = "Falhas:\n" + "\n".join([f"{path}: {err}" for path, err in results["failed"][:5]])
        if len(results["failed"]) > 5:
            error_msg += f"\n... e mais {len(results['failed']) - 5} erro(s)"
        
        messagebox.showwarning("Atenção", 
                              f"{success_count} arquivo(s) movido(s) com sucesso.\n"
                              f"{failed_count} falha(s).\n\n{error_msg}", 
                              parent=dialog)
    
    # Reativa botões
    for widget in dialog.winfo_children():
        if isinstance(widget, Button):
            widget.config(state='normal')
    
    # Atualiza a lista de arquivos no aplicativo principal
    if success_count > 0:
        # Remove os arquivos movidos da lista de arquivos
        app_instance.file_paths = [f for f in app_instance.file_paths 
                                  if f not in [pair[0] for pair in results["success"]]]
        app_instance.update_file_label()
        
        # Sugere recarregar resultados
        if app_instance.results:
            if messagebox.askyesno("Atualizar Resultados", 
                                 "Alguns arquivos foram movidos. Deseja limpar os resultados atuais?", 
                                 parent=app_instance.root):
                app_instance.clear_results()
