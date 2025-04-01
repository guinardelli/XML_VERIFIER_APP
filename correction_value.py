# correction_value.py

import os
import shutil
import re
import threading
from tkinter import messagebox
from lxml import etree
from typing import List, Tuple, Dict, TYPE_CHECKING

# Importa do projeto local
from .constants import DEFAULT_ENCODING

# Evita importação circular para type hinting
if TYPE_CHECKING:
    from .main_app import XMLVerifier

# --- Funções de Correção de Valor (Lógica Interna) ---

def _find_element_by_location(root: etree._Element, location_str: str) -> etree._Element | None:
    """
    Encontra um elemento lxml com base na string de localização gerada.
    Retorna o elemento lxml ou None se não encontrado.
    (Função auxiliar movida para cá, pois é específica desta correção)
    """
    try:
        # Remover a parte da linha: " (Linha XX)" ou " (Próximo à Linha XX)"
        path_part = re.sub(r'\s+\(.*?Linha\s+\d+\)$', '', location_str).strip()
        xpath_expression = f".//{path_part}"
        found_elements = root.xpath(xpath_expression)

        if found_elements:
            return found_elements[0]
        else:
            # Tentar abordagem passo a passo (código omitido por brevidade, igual ao anterior)
            parts = path_part.split('/')
            current_elements = [root]
            for part in parts:
                next_elements = []
                tag_name = part
                index = 0
                match = re.match(r"([a-zA-Z0-9_:]+)\[(\d+)\]", part)
                if match:
                    tag_name = match.group(1)
                    index = int(match.group(2))
                found_in_level = []
                for elem in current_elements:
                    children = elem.xpath(f"./{tag_name}")
                    found_in_level.extend(children)
                if not found_in_level: return None
                if index > 0:
                    if index <= len(found_in_level): next_elements.append(found_in_level[index - 1])
                    else: return None
                else:
                     if found_in_level: next_elements.append(found_in_level[0])
                if not next_elements: return None
                current_elements = next_elements
            if current_elements: return current_elements[0]
            else: return None
    except Exception as e:
        print(f"Erro ao tentar encontrar elemento por localização '{location_str}': {e}")
        return None

# --- Funções de Orquestração (Chamadas pela UI) ---

def start_manual_value_correction(app_instance: 'XMLVerifier'):
    """Inicia o processo de correção de valor para o(s) item(ns) selecionado(s)."""
    if app_instance.is_verifying or app_instance.is_fixing or app_instance.is_correcting_value:
        messagebox.showwarning("Aguarde", "Outra operação já está em andamento.", parent=app_instance.root)
        return

    selected_ids = app_instance.result_tree.selection()
    if not selected_ids:
        messagebox.showerror("Erro", "Selecione um ou mais itens na tabela de resultados para corrigir.", parent=app_instance.root)
        return

    correction_value = app_instance.correction_value_var.get()

    tasks_to_process: List[Tuple[str, str, str, str]] = [] # (file_path, location_str, new_value, item_id)
    files_involved = set()
    path_map = {os.path.basename(p): p for p in app_instance.file_paths}

    for item_id in selected_ids:
        try:
            item_values = app_instance.result_tree.item(item_id, "values")
            if not item_values: continue
            arquivo_base, _, _, localizacao = item_values
            file_path = path_map.get(arquivo_base)
            if not file_path or not os.path.exists(file_path): continue
            files_involved.add(arquivo_base)
            tasks_to_process.append((file_path, localizacao, correction_value, item_id))
        except Exception:
             messagebox.showwarning("Aviso", f"Não foi possível processar o item selecionado {item_id}.", parent=app_instance.root)


    if not tasks_to_process:
        messagebox.showerror("Erro", "Nenhum item válido selecionado ou encontrado para correção.", parent=app_instance.root)
        return

    num_items = len(tasks_to_process)
    num_files = len(files_involved)
    if not messagebox.askyesno("Confirmar Correção de Valor",
                               f"Você selecionou {num_items} item(ns) em {num_files} arquivo(s).\n\n"
                               f"O valor em cada localização selecionada será substituído por:\n'{correction_value}'\n\n"
                               f"Deseja continuar? (Serão criados backups .bak)", parent=app_instance.root):
        return

    app_instance.is_correcting_value = True
    app_instance.disable_buttons()
    app_instance.update_status(f"Corrigindo {num_items} valor(es) em {num_files} arquivo(s)...")

    threading.Thread(target=manual_value_correction_thread,
                     args=(app_instance, tasks_to_process,),
                     daemon=True).start()

def manual_value_correction_thread(app_instance: 'XMLVerifier', tasks: List[Tuple[str, str, str, str]]):
    """Thread para realizar a correção de múltiplos valores em arquivos XML."""
    results: Dict[str, List] = {'success': [], 'failed': []}
    tasks_by_file: Dict[str, List[Tuple[str, str, str]]] = {}

    for file_path, loc, val, item_id in tasks:
        if file_path not in tasks_by_file: tasks_by_file[file_path] = []
        tasks_by_file[file_path].append((loc, val, item_id))

    for file_path, file_tasks in tasks_by_file.items():
        made_changes_in_file = False
        backup_path = file_path + '.bak'
        tree = None
        root = None
        file_success_items = []
        file_failed_items = []
        base_name = os.path.basename(file_path) # Para mensagens de erro

        try:
            # Backup
            try: shutil.copy2(file_path, backup_path)
            except Exception as e:
                err_msg = f"Falha ao criar backup '{base_name}': {e}"
                for loc, val, item_id in file_tasks: file_failed_items.append((item_id, loc, err_msg, base_name))
                results['failed'].extend(file_failed_items)
                continue

            # Parse
            try:
                parser = etree.XMLParser(remove_blank_text=False, encoding=DEFAULT_ENCODING)
                tree = etree.parse(file_path, parser)
                root = tree.getroot()
            except Exception as e:
                err_msg = f"Falha ao analisar XML '{base_name}': {e}"
                for loc, val, item_id in file_tasks: file_failed_items.append((item_id, loc, err_msg, base_name))
                results['failed'].extend(file_failed_items)
                continue

            # Processar tarefas no arquivo
            for loc, new_value, item_id in file_tasks:
                try:
                    target_element = _find_element_by_location(root, loc)
                    if target_element is None: raise Exception(f"Elemento não encontrado: {loc}")
                    target_element.text = new_value
                    made_changes_in_file = True
                    file_success_items.append((item_id, loc, base_name)) # Adiciona basename para finalize
                except Exception as e:
                    file_failed_items.append((item_id, loc, str(e), base_name)) # Adiciona basename

            # Salvar se houve mudanças
            if made_changes_in_file:
                try:
                    etree.indent(tree, space="  ")
                    tree.write(file_path, encoding=DEFAULT_ENCODING, xml_declaration=True, pretty_print=False)
                    results['success'].extend(file_success_items)
                    results['failed'].extend(file_failed_items)
                except Exception as e:
                    err_msg = f"Erro ao salvar '{base_name}': {e}"
                    current_file_failures = []
                    for item_id_succ, loc_succ, fname_succ in file_success_items: current_file_failures.append((item_id_succ, loc_succ, err_msg, fname_succ))
                    for item_id_fail, loc_fail, _, fname_fail in file_failed_items: current_file_failures.append((item_id_fail, loc_fail, err_msg, fname_fail))
                    results['failed'].extend(current_file_failures)
            else:
                results['failed'].extend(file_failed_items)

        except Exception as e:
            err_msg = f"Erro inesperado processando '{base_name}': {e}"
            for loc, val, item_id in file_tasks: results['failed'].append((item_id, loc, err_msg, base_name))

    app_instance.root.after(0, finalize_manual_value_correction, app_instance, results)

def finalize_manual_value_correction(app_instance: 'XMLVerifier', results: Dict[str, List]):
    """Atualiza a UI após a tentativa de correção de múltiplos valores."""
    num_success = len(results['success'])
    num_failed = len(results['failed'])
    total_attempted = num_success + num_failed

    if total_attempted == 0:
        messagebox.showwarning("Correção", "Nenhuma operação de correção foi efetivamente tentada.", parent=app_instance.root)
        app_instance.reset_ui_state()
        return

    msg_title = "Resultado da Correção de Valor"
    msg_details = f"{num_success} de {total_attempted} valor(es) corrigido(s) com sucesso.\n"
    if num_failed > 0:
        msg_details += f"{num_failed} falha(s):\n"
        max_failures_to_show = 10
        for i, (item_id, loc, error_str, file_name) in enumerate(results['failed']):
             if i < max_failures_to_show:
                 msg_details += f"- Arq: {file_name}, Loc: {loc} -> Erro: {error_str}\n"
             elif i == max_failures_to_show:
                 msg_details += "- ... (mais falhas omitidas)\n"

    if num_failed == 0:
        messagebox.showinfo(msg_title, msg_details + "\nBackups (.bak) foram criados.", parent=app_instance.root)
        app_instance.status_var.set(f"{num_success} valor(es) corrigido(s).")
    elif num_success > 0:
        messagebox.showwarning(msg_title, msg_details + "\nVerifique os detalhes. Backups (.bak) foram criados.", parent=app_instance.root)
        app_instance.status_var.set(f"{num_success} sucesso(s), {num_failed} falha(s).")
    else:
        messagebox.showerror(msg_title, msg_details + "\nNenhum valor corrigido.", parent=app_instance.root)
        app_instance.status_var.set(f"Falha ao corrigir {num_failed} valor(es).")

    # Limpar resultados e pedir revalidação
    app_instance.clear_results()
    app_instance.status_var.set(f"Correção de valor concluída. Revalide os arquivos.")
    app_instance.reset_ui_state()