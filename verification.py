# verification.py

import os
import re
from lxml import etree
from typing import List, Tuple, Optional

# Importa constantes do módulo local
from .constants import (
    REQUIRED_FIELDS, NUMERIC_FIELDS, DEFAULT_ENCODING,
    ALLOWED_MULTIPLE_PECA_CHILDREN
)

# --- Funções Auxiliares (Específicas da Verificação) ---

def _get_element_line(element) -> Optional[int]:
    """Tenta obter o número da linha de um elemento lxml."""
    try:
        return getattr(element, 'sourceline', None)
    except Exception:
        return None

def _format_location(element, base_path: str) -> str:
    """Formata a string de localização incluindo a linha, se disponível."""
    line = _get_element_line(element)
    if line is not None:
        return f"{base_path} (Linha {line})"
    else:
        # Tenta a linha do pai se a do elemento falhar
        parent = element.getparent()
        if parent is not None:
            parent_line = _get_element_line(parent)
            if parent_line is not None:
                return f"{base_path} (Próximo à Linha {parent_line})"
    return base_path # Retorna só o path se não achar linha

# --- Funções de Verificação Específicas (Checks) ---
# Estas funções agora retornam uma lista de tuplas de erro/aviso encontradas
# (type: str, description: str, location_str: str)

def _check_ids_vs_pecas(peca: etree._Element, peca_idx: int) -> List[Tuple[str, str, str]]:
    results = []
    peca_location_base = f"PECA[{peca_idx+1}]"

    quantidade_elem = peca.find("./QUANTIDADE")
    if quantidade_elem is None or not quantidade_elem.text:
        loc = _format_location(peca, peca_location_base) # Localização da PECA se QUANTIDADE falta
        results.append(("Erro", "Campo 'QUANTIDADE' não encontrado ou vazio", loc))
        return results # Não pode continuar sem quantidade

    try:
        quantidade_text = quantidade_elem.text.strip().replace(',', '.')
        quantidade = int(float(quantidade_text))
    except (ValueError, TypeError):
        loc = _format_location(quantidade_elem, f"{peca_location_base}/QUANTIDADE")
        results.append(("Erro", f"Valor de QUANTIDADE ('{quantidade_elem.text}') não é um número inteiro válido", loc))
        return results # Não pode comparar IDs se quantidade é inválida

    ids_peca_elems = peca.findall("./LISTAID/ID")
    num_ids_peca = len(ids_peca_elems)

    if num_ids_peca != quantidade:
        listaid_elem = peca.find("./LISTAID")
        base_loc = f"{peca_location_base}/LISTAID"
        loc = _format_location(listaid_elem, base_loc) if listaid_elem is not None else _format_location(peca, peca_location_base)
        results.append(("Erro", f"Número de IDs em LISTAID ({num_ids_peca}) não corresponde à QUANTIDADE ({quantidade})", loc))

    return results

def _check_required_fields(peca: etree._Element, peca_idx: int) -> List[Tuple[str, str, str]]:
    results = []
    peca_location_base = f"PECA[{peca_idx+1}]"
    for field in REQUIRED_FIELDS:
        elem = peca.find(f"./{field}")
        loc_path = f"{peca_location_base}/{field}"
        if elem is None:
            loc = _format_location(peca, peca_location_base) # Localização da PECA se campo falta
            results.append(("Erro", f"Campo obrigatório '{field}' não encontrado", loc))
        else:
            loc = _format_location(elem, loc_path)
            if elem.text is None:
                results.append(("Erro", f"Campo obrigatório '{field}' está vazio (nulo)", loc))
            elif not elem.text.strip():
                results.append(("Erro", f"Campo obrigatório '{field}' contém apenas espaços", loc))
    return results

def _check_numeric_fields(peca: etree._Element, peca_idx: int) -> List[Tuple[str, str, str]]:
    results = []
    peca_location_base = f"PECA[{peca_idx+1}]"
    for field in NUMERIC_FIELDS:
        elem = peca.find(f"./{field}")
        if elem is not None and elem.text:
            try:
                clean_text = elem.text.strip().replace(',', '.')
                float(clean_text)
            except (ValueError, TypeError):
                loc = _format_location(elem, f"{peca_location_base}/{field}")
                results.append(("Erro", f"Campo '{field}' contém valor não numérico: '{elem.text}'", loc))
    return results

def _check_zero_qty_in_aco(peca: etree._Element, peca_idx: int) -> List[Tuple[str, str, str]]:
    results = []
    peca_location_base = f"PECA[{peca_idx+1}]"
    for pos_idx, posicao in enumerate(peca.findall(".//TABELAACO/POSICAO")):
        posicao_location_base = f"{peca_location_base}/TABELAACO/POSICAO[{pos_idx+1}]"
        qtde_elem = posicao.find("./QTDE")
        if qtde_elem is not None and qtde_elem.text:
            try:
                qtde_valor = float(qtde_elem.text.strip().replace(',', '.'))
                if qtde_valor == 0:
                    pos_elem = posicao.find("./POS")
                    pos_text = pos_elem.text.strip() if pos_elem is not None and pos_elem.text else f"Posição {pos_idx+1}"
                    loc = _format_location(qtde_elem, f"{posicao_location_base}/QTDE")
                    results.append(("Aviso", f"Armadura '{pos_text}' com quantidade zero (QTDE=0)", loc))
            except (ValueError, TypeError):
                pass # Erro numérico já pego por _check_numeric_fields
    return results

def _check_duplicated_fields(peca: etree._Element, peca_idx: int) -> List[Tuple[str, str, str]]:
    results = []
    peca_location_base = f"PECA[{peca_idx+1}]"
    tag_counts = {}
    first_occurrence_location = {}

    for child in peca:
        if isinstance(child.tag, str):
            tag = child.tag
            if tag not in ALLOWED_MULTIPLE_PECA_CHILDREN:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
                if tag not in first_occurrence_location:
                     loc_path = f"{peca_location_base}/{tag}"
                     first_occurrence_location[tag] = _format_location(child, loc_path)

    for tag, count in tag_counts.items():
        if count > 1:
            loc = first_occurrence_location.get(tag, _format_location(peca, peca_location_base))
            results.append(("Erro", f"Campo '{tag}' aparece {count} vezes (deveria ser único sob PECA)", loc))
    return results

def _check_xml_hierarchy(peca: etree._Element, peca_idx: int) -> List[Tuple[str, str, str]]:
    results = []
    peca_location_base = f"PECA[{peca_idx+1}]"
    peca_loc_str = _format_location(peca, peca_location_base)

    ids_diretos = peca.xpath("./ID")
    if ids_diretos:
        loc = _format_location(ids_diretos[0], f"{peca_location_base}/ID")
        results.append(("Erro", "Encontrado(s) tag(s) <ID> diretamente sob <PECA>. Devem estar dentro de <LISTAID>.", loc))

    listaid = peca.find("./LISTAID")
    if listaid is None and peca.xpath(".//ID"):
         results.append(("Erro", "Tag <LISTAID> não encontrada diretamente sob <PECA>, mas existem IDs na peça.", peca_loc_str))

    posicoes_diretas = peca.xpath("./POSICAO")
    if posicoes_diretas:
        loc = _format_location(posicoes_diretas[0], f"{peca_location_base}/POSICAO")
        results.append(("Erro", "Encontrado(s) tag(s) <POSICAO> diretamente sob <PECA>. Devem estar dentro de <TABELAACO>.", loc))

    tabelaaco = peca.find("./TABELAACO")
    if tabelaaco is None and peca.xpath(".//POSICAO"):
         results.append(("Erro", "Tag <TABELAACO> não encontrada diretamente sob <PECA>, mas existem POSICOES na peça.", peca_loc_str))

    return results

def _check_global_duplicate_ids(root: etree._Element) -> List[Tuple[str, str, str]]:
    """Verifica IDs duplicados em todo o documento."""
    results = []
    all_id_elems = root.findall(".//ID")
    all_id_values = [elem.text.strip() for elem in all_id_elems if elem.text]
    duplicates = set([x for x in all_id_values if all_id_values.count(x) > 1])

    if duplicates:
        first_occurrence_locations = {}
        # Encontra a localização da primeira ocorrência de cada duplicado
        processed_dups = set()
        for elem in all_id_elems:
            val = elem.text.strip() if elem.text else ""
            if val in duplicates and val not in processed_dups:
                 # Tenta encontrar o caminho relativo à PECA pai
                 peca_parent = elem.xpath("./ancestor::PECA")
                 loc_str = "Raiz do Documento" # Default
                 if peca_parent:
                     peca_list = root.findall(".//PECA")
                     try:
                         peca_idx = peca_list.index(peca_parent[0]) + 1
                         loc_str = _format_location(elem, f"PECA[{peca_idx}]/.../ID") # Simplificado
                     except ValueError:
                         loc_str = _format_location(elem, f"PECA[?]/.../ID")
                 else: # ID fora de uma PECA?
                     loc_str = _format_location(elem, f"/{elem.tag}") # Caminho absoluto simplificado

                 first_occurrence_locations[val] = loc_str
                 processed_dups.add(val)


        for dup in duplicates:
            loc = first_occurrence_locations.get(dup, "Localização Desconhecida")
            results.append(("Erro", f"ID duplicado encontrado no arquivo: '{dup}'", loc))
    return results


# --- Função Principal de Verificação ---

def run_verification_checks(file_path: str) -> List[Tuple[str, str, str, str]]:
    """
    Executa todas as verificações em um único arquivo XML.
    Retorna uma lista de resultados: [(file_basename, type, description, location_str)]
    """
    base_name = os.path.basename(file_path)
    results = [] # Lista de (type, description, location_str) para este arquivo

    try:
        parser = etree.XMLParser(remove_blank_text=False, recover=True, encoding=DEFAULT_ENCODING)
        tree = etree.parse(file_path, parser)
        root = tree.getroot()

        # Adiciona avisos de erros de parsing recuperados
        if parser.error_log:
            for error in parser.error_log:
                 if "DTD" not in error.message and "Entity" not in error.message:
                    loc = f"Linha {error.line}, Coluna {error.column}"
                    results.append(("Aviso", f"XML com problema (ignorado por recover=True): {error.message}", loc))

        # Executa verificações globais
        results.extend(_check_global_duplicate_ids(root))

        # Executa verificações por PECA
        pecas = root.findall(".//PECA")
        for peca_idx, peca in enumerate(pecas):
            results.extend(_check_ids_vs_pecas(peca, peca_idx))
            results.extend(_check_required_fields(peca, peca_idx))
            results.extend(_check_numeric_fields(peca, peca_idx))
            results.extend(_check_zero_qty_in_aco(peca, peca_idx))
            results.extend(_check_duplicated_fields(peca, peca_idx))
            results.extend(_check_xml_hierarchy(peca, peca_idx))

    except etree.XMLSyntaxError as e:
        # Erro fatal de parsing
        results.append(("Erro", f"XML mal formado (erro fatal): {str(e)}", f"Linha {e.lineno}"))
        # Poderia tentar a verificação baseada em texto aqui se necessário
        # results.extend(_check_xml_structure_text(file_path))

    except Exception as e:
        # Outro erro inesperado durante a verificação
        results.append(("Erro", f"Erro inesperado na verificação: {str(e)}", "Geral"))

    # Formata o resultado final adicionando o nome do arquivo base
    final_results = [(base_name, r_type, desc, loc) for r_type, desc, loc in results]
    return final_results

# (Opcional: Função _check_xml_structure_text(file_path) pode ser adicionada aqui se a verificação baseada em texto for desejada como fallback)