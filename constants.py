# constants.py

# Constantes para nomes de campos
REQUIRED_FIELDS = [
    "NOMEPECA", "TIPOPRODUTO", "GRUPO", "SECAO", "QUANTIDADE",
    "COMPRIMENTO", "ALTURA", "LARGURA", "VOLUMEUNITARIO",
    "PESO", "AREA", "CLASSECONCRETO", "DESENHO"
]

NUMERIC_FIELDS = [
    "QUANTIDADE", "COMPRIMENTO", "ALTURA", "LARGURA",
    "VOLUMEUNITARIO", "PESO", "AREA"
]

# Codificação padrão assumida para os arquivos XML Tekla
DEFAULT_ENCODING = 'ISO-8859-1'

# Tags que são permitidas ter múltiplas ocorrências diretas sob PECA
ALLOWED_MULTIPLE_PECA_CHILDREN = {"TABELAACO", "LISTAID"}

# Tag raiz esperada (para correção manual de estrutura)
DEFAULT_ROOT_TAG = "DETALHAMENTOTEKLA"