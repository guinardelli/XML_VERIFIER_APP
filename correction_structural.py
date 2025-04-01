# correction_structural.py

import os
import shutil
import re
import threading
from tkinter import messagebox
from lxml import etree
from typing import List, Tuple, TYPE_CHECKING

# Importa do projeto local
from .constants import DEFAULT_ENCODING, ALLOWED_MULTIPLE_PECA_CHILDREN, DEFAULT_ROOT_TAG
from .verification import run_verification_checks # Para revalidação

# Evita importação circular para type hinting
if TYPE_CHECKING:
    from .main_app import XMLVerifier

# --- Funções de Correção Estrutural (Lógica Interna) ---

def _fix_xml_hierarchy_lxml(root: etree._Element) -> bool:
    """Tenta corrigir a hierarquia (IDs/POSICAOs) usando lxml. Retorna True se fez mudanças."""
    made_changes = False
    for peca_idx, peca in enumerate(root.findall(".//PECA")):
        peca_changed = False
        # 1. Mover IDs soltos para LISTAID
        ids_diretos = peca.xpath("./ID")
        if ids_diretos:
            listaid = peca.find("./LISTAID")
            if listaid is None:
                listaid = etree.Element("LISTAID")
                peca.insert(peca.index(ids_diretos[0]), listaid)
                peca_changed = True
            for id_elem in ids_diretos: listaid.append(id_elem)
            peca_changed = True

        # 2. Mover POSICAOs soltas para TABELAACO
        posicoes_diretas = peca.xpath("./POSICAO")
        if posicoes_diretas:
            tabelaaco = peca.find("./TABELAACO")
            if tabelaaco is None:
                tabelaaco = etree.Element("TABELAACO")
                peca.insert(peca.index(posicoes_diretas[0]), tabelaaco)
                peca_changed = True
            for pos_elem in posicoes_diretas: tabelaaco.append(pos_elem)
            peca_changed = True

        if peca_changed:
            made_changes = True
    return made_changes

def _fix_xml_structure_manual_text(file_path: str) -> Tuple[bool, List[Tuple[str, str, str]]]:
    """Tenta corrigir estrutura básica (tags não fechadas) via texto.
       Retorna (True/False se mudou, lista de mensagens geradas)."""
    made_changes = False
    messages = [] # (type, description, location)
    try:
        with open(file_path, 'r', encoding=DEFAULT_ENCODING) as f: content = f.read()
        original_content = content

        root_tag = DEFAULT_ROOT_TAG
        open_tag_re = re.compile(rf'<{root_tag}[^>]*>', re.IGNORECASE)
        close_tag_re = re.compile(rf'</{root_tag}\s*>', re.IGNORECASE)

        if open_tag_re.search(content) and not close_tag_re.search(content):
            content = content.rstrip() + f"\n</{root_tag}>"
            made_changes = True
            messages.append(("Info", f"Adicionada tag de fechamento ausente </{root_tag}>.", "Correção Manual Estrutura"))

        peca_open_re = re.compile(r'<PECA[^>]*>', re.IGNORECASE)
        peca_close_re = re.compile(r'</PECA\s*>', re.IGNORECASE)
        open_count = len(peca_open_re.findall(content))
        close_count = len(peca_close_re.findall(content))

        if open_count > close_count:
             missing_count = open_count - close_count
             closing_tags = ("</PECA>\n" * missing_count)
             content = close_tag_re.sub(f"{closing_tags}</{root_tag}>", content, count=1)
             made_changes = True
             messages.append(("Info", f"Tentativa de adicionar {missing_count} tag(s) </PECA> ausente(s) antes de </{root_tag}>.", "Correção Manual Estrutura"))

        if made_changes and content.strip() != original_content.strip():
            try:
                with open(file_path, 'w', encoding=DEFAULT_ENCODING) as f: f.write(content)
                messages.append(("Info", "Arquivo modificado por correção estrutural manual.", "Correção Manual Estrutura"))
                return True, messages
            except Exception as e:
                messages.append(("Erro", f"Erro ao salvar arquivo após correção manual: {e}", "Escrita Pós-Manual"))
                return False, messages
        else:
            return False, messages

    except Exception as e:
        messages.append(("Erro", f"Erro inesperado durante correção estrutural manual: {str(e)}", "Correção Manual Estrutura"))
        return False, messages

def _fix_single_file_structure(file_path: str, backup: bool) -> Tuple[bool, List[Tuple[str, str, str]]]:
    """Coordena a correção estrutural para um arquivo, tentando lxml e fallback manual.
       Retorna (True/False se alguma correção foi feita e salva, lista de mensagens)."""
    base_name = os.path.basename(file_path)
    messages = [] # (type, description, location)
    made_changes = False
    backup_path = file_path + '.bak'

    # --- Backup ---
    if backup:
        try:
            shutil.copy2(file_path, backup_path)
        except Exception as e:
             messages.append(("Erro", f"Falha ao criar backup: {e}. Correção estrutural abortada.", "Backup"))
             return False, messages

    # --- Tentativa de Correção com lxml ---
    try:
        parser = etree.XMLParser(remove_blank_text=False, recover=True, encoding=DEFAULT_ENCODING)
        tree = etree.parse(file_path, parser)
        root = tree.getroot()

        lxml_fixed_hierarchy = _fix_xml_hierarchy_lxml(root)

        if lxml_fixed_hierarchy:
            try:
                etree.indent(tree, space="  ")
                tree.write(file_path, encoding=DEFAULT_ENCODING, xml_declaration=True, pretty_print=False)
                messages.append(("Info", "Hierarquia XML corrigida (IDs/POSICAOs movidos).", "Correção Estrutural lxml"))
                made_changes = True
                # Mesmo que lxml corrija, não retorna ainda, pois pode haver erros de parsing que o manual pegaria
                # return True, messages # <- Não retorna aqui
            except Exception as e:
                 messages.append(("Erro", f"Erro ao salvar arquivo após correção lxml: {e}", "Escrita Pós-lxml"))
                 return False, messages # Falha crítica ao salvar

        # Se lxml não fez mudanças ou mesmo se fez, continua para possível correção manual
        # (útil se lxml parseou com recover=True mas ainda há tags não fechadas)

    except etree.XMLSyntaxError as e:
        # lxml falhou completamente, tentar correção manual
        messages.append(("Aviso", f"lxml falhou no parsing inicial (Erro: {e}). Tentando correção estrutural manual.", "Correção Manual Fallback"))
        manual_fixed, manual_messages = _fix_xml_structure_manual_text(file_path)
        messages.extend(manual_messages)
        return manual_fixed, messages # Retorna o resultado da tentativa manual

    except Exception as e_lxml:
        # Outro erro durante o processamento com lxml
        messages.append(("Erro", f"Erro inesperado durante correção estrutural com lxml: {e_lxml}", "Correção Estrutural lxml"))
        # Tentar correção manual mesmo assim? Ou considerar falha? Considerar falha por segurança.
        return False, messages

    # Se chegou aqui, lxml parseou (talvez com recover) e pode ou não ter feito mudanças.
    # Tentar a correção manual PÓS lxml para pegar tags não fechadas que recover=True pode ter ignorado.
    # Nota: Isso pode ser redundante se lxml já salvou corretamente.
    # Decisão: Chamar a correção manual apenas se lxml falhou no parsing inicial (já feito acima).
    # Se lxml funcionou, confiamos que ele escreveu um XML válido (mesmo que tenha ignorado algo).
    return made_changes, messages


# --- Funções de Orquestração (Chamadas pela UI) ---

def start_structural_correction(app_instance: 'XMLVerifier'):
    """Inicia o processo de correção ESTRUTURAL (chamado pelo botão)."""
    if app_instance.is_fixing or app_instance.is_verifying or app_instance.is_correcting_value:
        messagebox.showwarning("Aguarde", "Outra operação já está em andamento.", parent=app_instance.root)
        return
    if not app_instance.file_paths:
        messagebox.showerror("Erro", "Por favor, selecione pelo menos um arquivo XML para corrigir.", parent=app_instance.root)
        return

    # Confirmações (lógica movida para cá)
    has_errors = any(r[1] == 'Erro' for r in app_instance.results)
    if not app_instance.results:
         if not messagebox.askyesno("Confirmar Correção Estrutural", "Nenhuma verificação foi feita ou nenhum problema encontrado.\nDeseja tentar a correção estrutural mesmo assim (pode reorganizar o XML)?", parent=app_instance.root): return
    elif not has_errors:
         if not messagebox.askyesno("Confirmar Correção Estrutural", "Nenhum 'Erro' foi detectado (apenas Avisos/Infos).\nDeseja tentar a correção estrutural mesmo assim (pode reorganizar o XML)?", parent=app_instance.root): return
    else:
         if not messagebox.askyesno("Confirmar Correção Estrutural", "Erros foram detectados. Deseja tentar a correção estrutural automática?\n(Isso tentará mover IDs/POSICAOs e fechar tags, mas NÃO corrigirá valores de dados).", parent=app_instance.root): return

    backup = messagebox.askyesno("Backup", "IMPORTANTE: Fazer backup (.bak) dos arquivos originais antes de tentar a correção estrutural?", parent=app_instance.root)

    app_instance.is_fixing = True
    app_instance.disable_buttons()
    app_instance.progress_frame.pack(fill=X, padx=5, pady=5)
    app_instance.progress_var.set(0)

    # Passa a instância da aplicação para a thread
    threading.Thread(target=structural_correction_thread, args=(app_instance, backup,), daemon=True).start()

def structural_correction_thread(app_instance: 'XMLVerifier', backup: bool):
    """Thread para corrigir a ESTRUTURA dos arquivos XML."""
    fixed_count = 0
    total_files = len(app_instance.file_paths)
    files_attempted_fix = []
    validation_errors_before = {}
    # Armazena resultados gerados pela própria correção + revalidação
    correction_and_validation_results = []

    # Copia resultados da verificação anterior para comparar antes/depois
    results_before_fix = list(app_instance.results)

    try:
        # 1. Tentar corrigir cada arquivo
        for i, file_path in enumerate(app_instance.file_paths):
            if not app_instance.is_fixing: break
            base_name = os.path.basename(file_path)
            app_instance.update_status(f"Corrigindo estrutura {i+1}/{total_files}: {base_name}")
            app_instance.progress_var.set(((i + 1) / total_files) * 50)

            # Contar erros ANTES da correção estrutural para este arquivo
            errors_before_count = sum(1 for r_fname, r_type, _, _ in results_before_fix if r_fname == base_name and r_type == 'Erro')
            validation_errors_before[base_name] = errors_before_count

            # Tentar corrigir ESTRUTURA
            try:
                fixed, messages = _fix_single_file_structure(file_path, backup)
                # Adiciona mensagens da correção aos resultados
                for msg_type, msg_desc, msg_loc in messages:
                    correction_and_validation_results.append((base_name, msg_type, msg_desc, msg_loc))
                if fixed:
                    fixed_count += 1
                files_attempted_fix.append(file_path)
            except Exception as e:
                correction_and_validation_results.append((base_name, "Erro", f"Erro crítico ao tentar corrigir estrutura: {str(e)}", "Correção Estrutural"))

        # 2. Revalidar os arquivos onde a correção foi tentada
        app_instance.update_status("Revalidando arquivos após correção estrutural...")
        app_instance.progress_var.set(50)
        validation_success_count = 0
        total_to_validate = len(files_attempted_fix)

        if total_to_validate > 0:
            for i, file_path in enumerate(files_attempted_fix):
                if not app_instance.is_fixing: break
                base_name = os.path.basename(file_path)
                app_instance.update_status(f"Validando arquivo {i+1}/{total_to_validate}: {base_name}")
                app_instance.progress_var.set(50 + (((i + 1) / total_to_validate) * 50))
                try:
                    # Executa a verificação novamente
                    validation_run_results = run_verification_checks(file_path)
                    correction_and_validation_results.extend(validation_run_results) # Adiciona resultados da validação

                    # Compara erros antes e depois
                    errors_after = sum(1 for r_fname, r_type, _, _ in validation_run_results if r_fname == base_name and r_type == 'Erro')
                    errors_before = validation_errors_before.get(base_name, 0)

                    if errors_after < errors_before:
                        validation_success_count += 1
                    elif errors_after > errors_before:
                         correction_and_validation_results.append((base_name, "Aviso", f"Número de erros aumentou após correção estrutural (Antes: {errors_before}, Depois: {errors_after})", "Validação Pós-Correção"))
                except Exception as e:
                    correction_and_validation_results.append((base_name, "Erro", f"Erro crítico ao validar após correção estrutural: {str(e)}", "Validação Pós-Correção"))

        # 3. Finalizar e atualizar UI na thread principal
        # Passa os novos resultados para a função finalize
        app_instance.root.after(0, finalize_structural_correction, app_instance, fixed_count, total_files, validation_success_count, total_to_validate, correction_and_validation_results)

    except Exception as e:
         print(f"Erro na thread de correção estrutural: {e}")
         app_instance.root.after(0, lambda: messagebox.showerror("Erro Fatal", f"Ocorreu um erro inesperado durante a correção estrutural:\n{e}", parent=app_instance.root))
         app_instance.root.after(0, app_instance.reset_ui_state)

def finalize_structural_correction(app_instance: 'XMLVerifier', fixed_count: int, total_files: int, validation_success_count: int, total_validated: int, final_results: List[Tuple[str, str, str, str]]):
    """Atualiza a UI após a conclusão da thread de correção ESTRUTURAL."""
    # Atualiza a lista de resultados principal da aplicação
    app_instance.results = final_results
    app_instance.apply_filters() # Exibe os novos resultados

    msg = f"Correção Estrutural concluída. {fixed_count}/{total_files} arquivos tiveram tentativas de correção aplicadas.\n"
    if total_validated > 0:
        msg += f"{validation_success_count}/{total_validated} arquivos validados apresentaram menos erros após a correção."
    else:
         msg += "Nenhum arquivo foi revalidado."

    app_instance.status_var.set(f"Correção Estrutural concluída. {fixed_count} arquivos modificados.")
    messagebox.showinfo("Correção Estrutural Concluída", msg, parent=app_instance.root)
    app_instance.reset_ui_state()