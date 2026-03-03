"""
Bot Financeiro - Telegram + Google Sheets
==========================================
Comandos (mande como texto normal, sem /):

  gasto <valor> <descricao> <categoria>    -> registra despesa
  receita <valor> <descricao> <categoria>  -> registra receita
  resumo                                   -> saldo do mes atual
  categorias                               -> lista categorias validas
  /start ou /ajuda                         -> mostra ajuda

Exemplos:
  gasto 834.14 Unimed Saude
  gasto 120 Mesada Davi Despesa Fixa
  receita 5200 Salario Renda Fixa
  receita 2200 Blue Tree Freela
  resumo
"""

import logging
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, filters, ContextTypes
)
import gspread
from google.oauth2.service_account import Credentials

# ============================================================
# CONFIGURACOES — edite estas 3 linhas
# ============================================================
TELEGRAM_TOKEN   = "8722885193:AAGJ2gPQupJkkDR3_vJUgHC_X8y_98ssUwE"           # Token do @BotFather
SPREADSHEET_ID   = "1DrehDy6YY7CwBWeeXgOXboSLwxeHYvrSM39W5klF1iA"  # ID do Google Sheets
CREDENTIALS_FILE = "credentials.json"          # Arquivo de credenciais
# ============================================================

# Categorias validas (devem bater EXATAMENTE com a planilha)
CATS_DESPESA = {
    "despesa fixa"  : "Despesa Fixa",
    "saude"         : "Saúde",
    "equipe"        : "Equipe",
    "cartao"        : "Cartão",
    "contrato"      : "Contrato",
    "outros"        : "Outros",
}
CATS_RECEITA = {
    "renda fixa"    : "Renda Fixa",
    "freela"        : "Freela",
    "contrato"      : "Contrato",
    "outros"        : "Outros",
}

# Nomes exatos das abas no Google Sheets
ABA_RECEITAS  = "Receitas"
ABA_DESPESAS  = "Despesas"
ABA_DASHBOARD = "Dashboard"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
log = logging.getLogger(__name__)

# ── Google Sheets ────────────────────────────────────────────
def conectar():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
    return gspread.authorize(creds).open_by_key(SPREADSHEET_ID)

def proxima_linha(sheet):
    col = sheet.col_values(2)  # coluna B = Data
    for i in range(5, len(col)):
        if not col[i]:
            return i + 1
    return max(len(col) + 1, 6)

def normalizar_categoria(texto, mapa):
    """Tenta encontrar a categoria correta mesmo com acentos/maiusculas errados."""
    t = texto.lower().strip()
    # busca exata
    if t in mapa:
        return mapa[t]
    # busca parcial
    for key, val in mapa.items():
        if t in key or key in t:
            return val
    return "Outros"

def registrar_despesa(valor, descricao, categoria):
    doc   = conectar()
    sheet = doc.worksheet(ABA_DESPESAS)
    linha = proxima_linha(sheet)
    hoje  = datetime.now().strftime("%d/%m/%Y")
    cat   = normalizar_categoria(categoria, CATS_DESPESA)
    sheet.update(
        range_name=f"B{linha}:H{linha}",
        values=[[hoje, descricao, cat, "", valor, "Pago", ""]]
    )
    return cat

def registrar_receita(valor, descricao, categoria):
    doc   = conectar()
    sheet = doc.worksheet(ABA_RECEITAS)
    linha = proxima_linha(sheet)
    hoje  = datetime.now().strftime("%d/%m/%Y")
    cat   = normalizar_categoria(categoria, CATS_RECEITA)
    sheet.update(
        range_name=f"B{linha}:G{linha}",
        values=[[hoje, descricao, cat, "", valor, ""]]
    )
    return cat

def buscar_resumo_mes():
    doc   = conectar()
    sheet = doc.worksheet(ABA_DASHBOARD)
    mes   = datetime.now().month
    linha = 10 + mes  # linha 11 = Jan, 22 = Dez
    rec  = float(str(sheet.cell(linha, 10).value or "0").replace(",", "."))
    desp = float(str(sheet.cell(linha, 11).value or "0").replace(",", "."))
    saldo = rec - desp
    return rec, desp, saldo

# ── Handlers Telegram ────────────────────────────────────────
AJUDA = (
    "Oi! Sou seu bot financeiro.\n\n"
    "Como usar:\n"
    "  gasto 50 almoco Saude\n"
    "  gasto 2600 Pensao Elias Despesa Fixa\n"
    "  receita 5200 Salario Renda Fixa\n"
    "  receita 18000 Pref Cafelandia Freela\n"
    "  resumo\n"
    "  categorias\n\n"
    "Dica: o valor usa ponto como decimal. Ex: 834.14"
)

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(AJUDA)

async def cmd_categorias(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    d = ", ".join(CATS_DESPESA.values())
    r = ", ".join(CATS_RECEITA.values())
    await update.message.reply_text(
        f"Categorias de despesa:\n{d}\n\nCategorias de receita:\n{r}"
    )

async def cmd_resumo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text("Buscando dados da planilha...")
        rec, desp, saldo = buscar_resumo_mes()
        mes  = datetime.now().strftime("%B de %Y")
        icone = "positivo" if saldo >= 0 else "NEGATIVO - atencao!"
        await update.message.reply_text(
            f"Resumo de {mes}\n"
            f"----------------------------\n"
            f"Receitas:  R$ {rec:>10,.2f}\n"
            f"Despesas:  R$ {desp:>10,.2f}\n"
            f"----------------------------\n"
            f"Saldo:     R$ {saldo:>10,.2f}  ({icone})"
        )
    except Exception as e:
        log.error(e)
        await update.message.reply_text(
            "Nao consegui buscar o resumo. Verifique se a planilha esta compartilhada com a conta de servico."
        )

async def processar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    texto  = update.message.text.strip()
    partes = texto.split(None, 3)

    primeiro = partes[0].lower() if partes else ""

    if primeiro in ("resumo",):
        await cmd_resumo(update, ctx)
        return
    if primeiro in ("categorias",):
        await cmd_categorias(update, ctx)
        return
    if primeiro in ("ajuda", "help"):
        await cmd_start(update, ctx)
        return

    if primeiro not in ("gasto", "receita"):
        await update.message.reply_text(
            "Nao entendi. Comece com 'gasto' ou 'receita'.\n"
            "Digite 'ajuda' para ver os comandos."
        )
        return

    if len(partes) < 3:
        await update.message.reply_text(
            "Faltou informacao. Formato:\n"
            "  gasto <valor> <descricao> <categoria>\n\n"
            "Exemplo: gasto 50 almoco Saude"
        )
        return

    try:
        valor = float(partes[1].replace(",", "."))
    except ValueError:
        await update.message.reply_text(
            "Valor invalido. Use ponto como decimal.\n"
            "Exemplo: gasto 834.14 Unimed Saude"
        )
        return

    descricao = partes[2]
    categoria = partes[3] if len(partes) == 4 else "Outros"

    try:
        await update.message.reply_text("Registrando na planilha...")
        if primeiro == "gasto":
            cat_real = registrar_despesa(valor, descricao, categoria)
            await update.message.reply_text(
                f"Despesa registrada!\n"
                f"Valor:      R$ {valor:,.2f}\n"
                f"Descricao:  {descricao}\n"
                f"Categoria:  {cat_real}\n"
                f"Data:       {datetime.now().strftime('%d/%m/%Y')}"
            )
        else:
            cat_real = registrar_receita(valor, descricao, categoria)
            await update.message.reply_text(
                f"Receita registrada!\n"
                f"Valor:      R$ {valor:,.2f}\n"
                f"Descricao:  {descricao}\n"
                f"Categoria:  {cat_real}\n"
                f"Data:       {datetime.now().strftime('%d/%m/%Y')}"
            )
    except Exception as e:
        log.error(e)
        await update.message.reply_text(
            "Erro ao salvar na planilha.\n"
            "Verifique se as configuracoes estao corretas (token, ID da planilha, credentials.json)."
        )

# ── Main ─────────────────────────────────────────────────────
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",      cmd_start))
    app.add_handler(CommandHandler("ajuda",      cmd_start))
    app.add_handler(CommandHandler("resumo",     cmd_resumo))
    app.add_handler(CommandHandler("categorias", cmd_categorias))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, processar))
    log.info("Bot financeiro rodando!")
    app.run_polling()

if __name__ == "__main__":
    main()
