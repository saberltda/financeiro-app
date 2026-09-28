import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import plotly.express as px
from sqlalchemy import create_engine, text
import streamlit.components.v1 as components
import hmac

st.set_page_config(
    page_title="Controle Motorista Pro", 
    page_icon="🚗", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Fuso horário oficial de Brasília
FUSO_SP = ZoneInfo("America/Sao_Paulo")

def obter_data_hoje():
    return datetime.now(FUSO_SP).date()

# Estilização visual moderna e compacta para celular
st.markdown("""
<style>
    div[data-testid="stMetricValue"] > div {
        font-size: 1.35rem !important;
        font-weight: 700 !important;
    }
    .stButton button {
        border-radius: 8px;
    }
    .card-km {
        padding: 14px 18px;
        border-radius: 10px;
        background-color: rgba(0, 204, 150, 0.08);
        border: 1px solid rgba(0, 204, 150, 0.25);
        margin-bottom: 14px;
    }
    div[data-testid="stDateInput"] input {
        caret-color: transparent !important;
        cursor: pointer !important;
    }
</style>
""", unsafe_allow_html=True)

# --- SISTEMA DE AUTENTICAÇÃO ---
def verificar_login():
    if "autenticado" not in st.session_state:
        st.session_state["autenticado"] = False

    if st.session_state["autenticado"]:
        return True

    col_vazia1, col_centro, col_vazia2 = st.columns([1, 2.5, 1])
    with col_centro:
        st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
        st.markdown("### 🔒 Acesso Restrito")
        st.caption("Digite suas credenciais para acessar o painel operacional.")

        with st.form("form_login"):
            usuario_input = st.text_input("Usuário", placeholder="Ex: admin").strip()
            senha_input = st.text_input("Senha", type="password", placeholder="••••••••")
            btn_entrar = st.form_submit_button("🔓 Entrar", use_container_width=True, type="primary")

            if btn_entrar:
                user_correto = st.secrets["auth"]["username"]
                senha_correta = st.secrets["auth"]["password"]

                valida_user = hmac.compare_digest(usuario_input, user_correto)
                valida_senha = hmac.compare_digest(senha_input, senha_correta)

                if valida_user and valida_senha:
                    st.session_state["autenticado"] = True
                    st.rerun()
                else:
                    st.error("Usuário ou senha incorretos.")

    return False

if not verificar_login():
    st.stop()

# --- BARRA SUPERIOR COM LOGOUT ---
c_titulo, c_sair = st.columns([4, 1.2])
with c_titulo:
    st.title("🚗 Gestão de Turnos & Finanças")
with c_sair:
    st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
    if st.button("🚪 Sair", use_container_width=True):
        st.session_state["autenticado"] = False
        st.rerun()

# Nomenclaturas fixas de categorias
OPCOES_RECEITA_FIXAS = ["Uber sem pedágios", "99 com pedágios", "Pedágio Uber", "Particular"]
OPCOES_DESPESA_FIXAS = ["Combustível", "Lavagem", "SemParar do dia"]

OPCOES_RECEITA_FORM = OPCOES_RECEITA_FIXAS + ["Outro"]
OPCOES_DESPESA_FORM = OPCOES_DESPESA_FIXAS + ["Outro"]

DIAS_SEMANA_PT = {
    0: "Segunda-feira",
    1: "Terça-feira",
    2: "Quarta-feira",
    3: "Quinta-feira",
    4: "Sexta-feira",
    5: "Sábado",
    6: "Domingo"
}

def formata_real(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def converter_valor(texto):
    if not texto:
        return 0.0
    texto_limpo = str(texto).strip().replace("R$", "").replace("r$", "").strip()
    if not texto_limpo:
        return 0.0
    if "," in texto_limpo and "." in texto_limpo:
        texto_limpo = texto_limpo.replace(".", "").replace(",", ".")
    elif "," in texto_limpo:
        texto_limpo = texto_limpo.replace(",", ".")
    try:
        val = float(texto_limpo)
        return val if val >= 0 else 0.0
    except ValueError:
        return -1.0

def converter_km(texto):
    if not texto:
        return None
    texto_limpo = str(texto).strip().replace(".", "").replace(",", ".")
    try:
        val = float(texto_limpo)
        return val if val >= 0 else None
    except ValueError:
        return None

# Conexão com Supabase
raw_url = st.secrets["database"]["url"]
if raw_url.startswith("postgresql://"):
    raw_url = raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
elif raw_url.startswith("postgres://"):
    raw_url = raw_url.replace("postgres://", "postgresql+psycopg://", 1)

if "sslmode" not in raw_url:
    raw_url += "?sslmode=require" if "?" not in raw_url else "&sslmode=require"

@st.cache_resource
def get_db_engine():
    return create_engine(raw_url, pool_pre_ping=True, pool_recycle=300)

engine = get_db_engine()

# Inicialização de tabelas (Lançamentos e Turnos de Quilometragem)
if "db_inicializado" not in st.session_state:
    try:
        with engine.begin() as conn:
            conn.execute(text('''
                CREATE TABLE IF NOT EXISTS lancamentos (
                    id SERIAL PRIMARY KEY,
                    data DATE NOT NULL,
                    tipo TEXT NOT NULL,
                    categoria TEXT NOT NULL,
                    descricao TEXT,
                    valor NUMERIC(10, 2) NOT NULL
                );
            '''))
            conn.execute(text('''
                CREATE TABLE IF NOT EXISTS turnos_km (
                    data DATE PRIMARY KEY,
                    km_inicial NUMERIC(10, 2),
                    km_final NUMERIC(10, 2),
                    km_rodado NUMERIC(10, 2)
                );
            '''))
        st.session_state["db_inicializado"] = True
    except Exception as e:
        st.error(f"Erro de conexão com o banco de dados: {str(e)}")
        st.stop()

# Operações de Banco de Dados com Cache
@st.cache_data(ttl=600)
def carregar_dados():
    with engine.connect() as conn:
        df = pd.read_sql_query(text("SELECT * FROM lancamentos ORDER BY data DESC, id DESC"), conn)
    if not df.empty:
        df["data"] = pd.to_datetime(df["data"])
        df["valor"] = df["valor"].astype(float)
        df["categoria"] = df["categoria"].replace({
            "Uber": "Uber sem pedágios",
            "99": "99 com pedágios"
        })
    return df

@st.cache_data(ttl=600)
def carregar_turnos_km():
    with engine.connect() as conn:
        df_km = pd.read_sql_query(text("SELECT * FROM turnos_km ORDER BY data DESC"), conn)
    if not df_km.empty:
        df_km["data"] = pd.to_datetime(df_km["data"])
        df_km["km_inicial"] = df_km["km_inicial"].astype(float)
        df_km["km_final"] = df_km["km_final"].astype(float)
        df_km["km_rodado"] = df_km["km_rodado"].astype(float)
    return df_km

def salvar_km_inicial(data_reg, km_ini):
    with engine.begin() as conn:
        conn.execute(text('''
            INSERT INTO turnos_km (data, km_inicial)
            VALUES (:data, :km_inicial)
            ON CONFLICT (data) DO UPDATE 
            SET km_inicial = EXCLUDED.km_inicial;
        '''), {"data": data_reg, "km_inicial": km_ini})
    carregar_turnos_km.clear()

def salvar_fechamento_turno(data_reg, km_ini, km_fim, km_rodado, lista_lancamentos):
    with engine.begin() as conn:
        # Salva o turno de KM
        conn.execute(text('''
            INSERT INTO turnos_km (data, km_inicial, km_final, km_rodado)
            VALUES (:data, :km_ini, :km_fim, :km_rodado)
            ON CONFLICT (data) DO UPDATE 
            SET km_inicial = EXCLUDED.km_inicial,
                km_final = EXCLUDED.km_final,
                km_rodado = EXCLUDED.km_rodado;
        '''), {"data": data_reg, "km_ini": km_ini, "km_fim": km_fim, "km_rodado": km_rodado})

        # Insere todos os lançamentos do checklist
        for l in lista_lancamentos:
            conn.execute(text('''
                INSERT INTO lancamentos (data, tipo, categoria, descricao, valor)
                VALUES (:data, :tipo, :categoria, :descricao, :valor)
            '''), {
                "data": data_reg,
                "tipo": l["tipo"],
                "categoria": l["categoria"],
                "descricao": l["descricao"],
                "valor": l["valor"]
            })
    carregar_dados.clear()
    carregar_turnos_km.clear()

def atualizar_registro(id_reg, data_reg, tipo, categoria, descricao, valor):
    with engine.begin() as conn:
        conn.execute(text('''
            UPDATE lancamentos
            SET data = :data, tipo = :tipo, categoria = :categoria, descricao = :descricao, valor = :valor
            WHERE id = :id
        '''), {"data": data_reg, "tipo": tipo, "categoria": categoria, "descricao": descricao, "valor": valor, "id": id_reg})
    carregar_dados.clear()

def deletar_registro(id_reg):
    with engine.begin() as conn:
        conn.execute(text('DELETE FROM lancamentos WHERE id = :id'), {"id": id_reg})
    carregar_dados.clear()

# Gerador de Dossiê Especial para IA com Métricas de KM
def gerar_dossie_ia(df_periodo, df_km_periodo, d_ini, d_end):
    if df_periodo.empty and df_km_periodo.empty:
        return "Nenhum dado encontrado para o período."

    df_local = df_periodo.copy()
    if not df_local.empty:
        df_local["dia_semana"] = df_local["data"].dt.dayofweek.map(DIAS_SEMANA_PT)
        tot_rec = df_local[df_local["tipo"] == "Receita"]["valor"].sum()
        tot_desp = df_local[df_local["tipo"] == "Despesa"]["valor"].sum()
    else:
        tot_rec, tot_desp = 0.0, 0.0

    lucro = tot_rec - tot_desp
    margem = (lucro / tot_rec * 100) if tot_rec > 0 else 0.0

    tot_km = df_km_periodo["km_rodado"].dropna().sum() if not df_km_periodo.empty else 0.0
    rec_por_km = (tot_rec / tot_km) if tot_km > 0 else 0.0
    custo_por_km = (tot_desp / tot_km) if tot_km > 0 else 0.0
    lucro_por_km = (lucro / tot_km) if tot_km > 0 else 0.0

    dias_trabalhados = df_local["data"].dt.date.nunique() if not df_local.empty else len(df_km_periodo)
    media_lucro_dia = (lucro / dias_trabalhados) if dias_trabalhados > 0 else 0.0
    media_km_dia = (tot_km / dias_trabalhados) if dias_trabalhados > 0 else 0.0

    rec_por_cat = df_local[df_local["tipo"] == "Receita"].groupby("categoria")["valor"].sum().to_dict() if not df_local.empty else {}
    desp_por_cat = df_local[df_local["tipo"] == "Despesa"].groupby("categoria")["valor"].sum().to_dict() if not df_local.empty else {}

    prompt_linhas = [
        "# RELATÓRIO OPERACIONAL E FINANCEIRO — MOTORISTA DE APLICATIVO",
        "",
        "## INSTRUÇÕES PARA A INTELIGÊNCIA ARTIFICIAL",
        "Você é um consultor financeiro e de estratégia operacional para motoristas de aplicativo.",
        "Analise os dados financeiros e MÉTRICAS DE QUILOMETRAGEM (R$/km, Custo/km e Lucro/km) para apontar como aumentar o lucro.",
        "",
        "### REGRAS CONTÁBEIS IMPORTANTES:",
        "- **99 com pedágios:** Já embute o reembolso dos pedágios.",
        "- **Uber sem pedágios:** Não inclui pedágios (estes estão sob 'Pedágio Uber').",
        "- **SemParar do dia / Pedágios:** Custo real pago pelo motorista. Não deduza pedágios duas vezes.",
        "",
        "### SEU DIAGNÓSTICO DEVE CONTER:",
        "1. **Eficiência por KM Rodado:** Análise se o retorno bruto por km e o custo operacional por km estão saudáveis.",
        "2. **Padrões de Eficiência Operacional:** Relação entre combustível gasto e quilometragem rodada.",
        "3. **3 Ações Práticas Imediatas:** Como rodar menos quilômetros vazios (bater lata) e maximizar o lucro líquido.",
        "",
        "---",
        "## 1. RESUMO EXECUTIVO DO PERÍODO",
        f"- **Período:** {d_ini.strftime('%d/%m/%Y')} até {d_end.strftime('%d/%m/%Y')}",
        f"- **Dias Trabalhados:** {dias_trabalhados} dia(s)",
        f"- **Quilometragem Total:** {tot_km:.1f} km (Média: {media_km_dia:.1f} km/dia)",
        f"- **Faturamento Bruto:** {formata_real(tot_rec)}",
        f"- **Despesas Totais:** {formata_real(tot_desp)}",
        f"- **Lucro Líquido:** {formata_real(lucro)}",
        f"- **Margem Líquida:** {margem:.1f}%",
        f"- **Retorno Bruto por KM (R$/km):** {formata_real(rec_por_km)} / km",
        f"- **Custo por KM Rodado:** {formata_real(custo_por_km)} / km",
        f"- **Lucro Líquido Real por KM:** {formata_real(lucro_por_km)} / km",
        f"- **Média de Lucro Líquido por Dia:** {formata_real(media_lucro_dia)} / dia",
        "",
        "---",
        "## 2. ORIGEM DAS RECEITAS"
    ]

    for cat, val in rec_por_cat.items():
        pct = (val / tot_rec * 100) if tot_rec > 0 else 0
        prompt_linhas.append(f"- **{cat}:** {formata_real(val)} ({pct:.1f}%)")

    prompt_linhas.extend(["", "---", "## 3. COMPOSIÇÃO DOS CUSTOS"])
    for cat, val in desp_por_cat.items():
        pct_rec = (val / tot_rec * 100) if tot_rec > 0 else 0
        prompt_linhas.append(f"- **{cat}:** {formata_real(val)} (consome {pct_rec:.1f}% da receita)")

    prompt_linhas.extend(["", "---", "## 4. REGISTRO DE TURNOS (KM)"])
    if not df_km_periodo.empty:
        for _, row in df_km_periodo.iterrows():
            k_rod = f"{row['km_rodado']:.1f} km" if pd.notnull(row['km_rodado']) else "Em aberto"
            k_ini = f"{row['km_inicial']:.1f}" if pd.notnull(row['km_inicial']) else "-"
            k_fim = f"{row['km_final']:.1f}" if pd.notnull(row['km_final']) else "-"
            prompt_linhas.append(f"- **{row['data'].strftime('%d/%m/%Y')}:** KM Inicial: {k_ini} | KM Final: {k_fim} | Rodados: {k_rod}")

    return "\n".join(prompt_linhas)

# Carregamento de dados
df_completo = carregar_dados()
df_turnos_km = carregar_turnos_km()

if "msg_sucesso" in st.session_state:
    st.success(st.session_state.pop("msg_sucesso"))

# Estado da data
if "data_turno" not in st.session_state:
    st.session_state["data_turno"] = obter_data_hoje()

if "date_key_ver" not in st.session_state:
    st.session_state["date_key_ver"] = 0

# Modal de Edição de Lançamento Individual
@st.dialog("✏️ Editar Lançamento")
def modal_editar_registro(item_id, item_data, item_tipo, item_cat, item_desc, item_val):
    badge = "🟢" if item_tipo == "Receita" else "🔴"
    st.markdown(f"**Tipo:** {badge} **{item_tipo}**")
    
    with st.form(f"form_ed_{item_id}"):
        novo_val_str = st.text_input("Valor (R$):", value=f"{float(item_val):.2f}".replace(".", ","))
        opcoes_lista = OPCOES_RECEITA_FORM if item_tipo == "Receita" else OPCOES_DESPESA_FORM
        idx = opcoes_lista.index(item_cat) if item_cat in opcoes_lista else opcoes_lista.index("Outro")
        cat_sel = st.selectbox("Categoria:", opcoes_lista, index=idx)
        cat_final = st.text_input("Especifique a categoria *", value=item_cat if cat_sel == "Outro" else "").strip() if cat_sel == "Outro" else cat_sel
        nova_desc = st.text_input("Observação:", value=item_desc if item_desc else "").strip()

        if st.form_submit_button("💾 Salvar Alterações", type="primary", use_container_width=True):
            v_num = converter_valor(novo_val_str)
            if v_num <= 0:
                st.error("Informe um valor maior que zero.")
            else:
                atualizar_registro(item_id, item_data, item_tipo, cat_final, nova_desc, v_num)
                st.session_state["msg_sucesso"] = f"Lançamento #{item_id} atualizado!"
                st.rerun()

@st.dialog("🗑️ Confirmar Exclusão")
def modal_excluir_registro(item_id, item_cat, item_val_formatado):
    st.write(f"Deseja excluir o lançamento **#{item_id}**?")
    st.markdown(f"**{item_cat}** — **{item_val_formatado}**")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✔️ Sim, excluir", type="primary", use_container_width=True):
            deletar_registro(item_id)
            st.session_state["msg_sucesso"] = "Lançamento excluído com sucesso!"
            st.rerun()
    with col2:
        if st.button("✖️ Cancelar", use_container_width=True):
            st.rerun()

# Abas Nativas
tab_turno, tab_gerenciar = st.tabs(["📋 Painel do Turno (KM & Fechamento)", "⚙️ Histórico & Lançamentos"])

# ==========================================
# ABA 1: PAINEL DO TURNO & FECHAMENTO DIÁRIO
# ==========================================
with tab_turno:
    # Seletor de Data com botões rápidos
    st.markdown("**Data de Referência do Turno:**")
    c_h, c_o, c_d = st.columns([1, 1, 2])
    with c_h:
        if st.button("📅 Hoje", use_container_width=True):
            st.session_state["data_turno"] = obter_data_hoje()
            st.session_state["date_key_ver"] += 1
            st.rerun()
    with c_o:
        if st.button("📅 Ontem", use_container_width=True):
            st.session_state["data_turno"] = obter_data_hoje() - timedelta(days=1)
            st.session_state["date_key_ver"] += 1
            st.rerun()
    with c_d:
        dt_sel = st.date_input(
            "Data",
            value=st.session_state["data_turno"],
            key=f"data_sel_turno_{st.session_state['date_key_ver']}",
            label_visibility="collapsed"
        )
        st.session_state["data_turno"] = dt_sel

    data_atual = st.session_state["data_turno"]
    st.caption(f"🗓️ Turno ativo: **{data_atual.strftime('%d/%m/%Y')}** ({DIAS_SEMANA_PT[data_atual.weekday()]})")

    # Busca registro de KM do dia selecionado
    turno_dia = df_turnos_km[df_turnos_km["data"].dt.date == data_atual]
    km_ini_gravado = turno_dia["km_inicial"].values[0] if not turno_dia.empty and pd.notnull(turno_dia["km_inicial"].values[0]) else None
    km_fim_gravado = turno_dia["km_final"].values[0] if not turno_dia.empty and pd.notnull(turno_dia["km_final"].values[0]) else None
    km_rod_gravado = turno_dia["km_rodado"].values[0] if not turno_dia.empty and pd.notnull(turno_dia["km_rodado"].values[0]) else None

    # PASSO 1: INÍCIO DO DIA (KM INICIAL)
    st.markdown("#### 1️⃣ Início do Turno: Quilometragem Inicial")
    if km_ini_gravado is not None:
        st.success(f"🟢 **KM Inicial Registrado:** **{km_ini_gravado:,.1f} km**".replace(",", "X").replace(".", ",").replace("X", "."))
    else:
        with st.form("form_km_inicial"):
            c_kmi, c_btnkmi = st.columns([2, 1])
            with c_kmi:
                input_kmi = st.text_input("KM do Odômetro ao sair de casa:", placeholder="Ex: 85420")
            with c_btnkmi:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                btn_salvar_kmi = st.form_submit_button("Salvar KM Inicial", use_container_width=True, type="primary")

            if btn_salvar_kmi:
                val_kmi = converter_km(input_kmi)
                if val_kmi is None or val_kmi <= 0:
                    st.error("Informe um KM inicial válido.")
                else:
                    salvar_km_inicial(data_atual, val_kmi)
                    st.session_state["msg_sucesso"] = f"KM Inicial ({val_kmi:.1f}) salvo com sucesso!"
                    st.rerun()

    st.markdown("---")

    # PASSO 2: CHECKLIST DE FECHAMENTO COMPLETO
    st.markdown("#### 2️⃣ Fim do Turno: Checklist de Fechamento")
    st.caption("Preencha o KM final e os valores do seu dia. Deixe zerado ou vazio o que não realizou.")

    with st.form("form_fechamento_turno"):
        # Campos de Quilometragem
        st.markdown("**Quilometragem:**")
        col_km1, col_km2 = st.columns(2)
        with col_km1:
            val_padrao_kmi = f"{km_ini_gravado:.1f}".replace(".", ",") if km_ini_gravado else ""
            txt_kmi = st.text_input("KM Inicial do dia:", value=val_padrao_kmi, placeholder="Ex: 85420")
        with col_km2:
            val_padrao_kmf = f"{km_fim_gravado:.1f}".replace(".", ",") if km_fim_gravado else ""
            txt_kmf = st.text_input("KM Final do dia:", value=val_padrao_kmf, placeholder="Ex: 85630")

        st.markdown("---")
        st.markdown("##### 🟢 Ganhos do Dia (Receitas):")
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            v_uber = st.text_input("Uber sem pedágios (R$):", placeholder="0,00")
            v_99 = st.text_input("99 com pedágios (R$):", placeholder="0,00")
        with col_r2:
            v_ped_uber = st.text_input("Reembolso Pedágio Uber (R$):", placeholder="0,00")
            v_part = st.text_input("Corridas Particulares (R$):", placeholder="0,00")

        st.markdown("##### 🔴 Despesas do Turno:")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            v_combustivel = st.text_input("Combustível (R$):", placeholder="0,00")
            v_semparar = st.text_input("SemParar do dia / Pedágios (R$):", placeholder="0,00")
        with col_d2:
            v_lavagem = st.text_input("Lavagem (R$):", placeholder="0,00")
            v_outra_desp = st.text_input("Outro Custo / Manutenção (R$):", placeholder="0,00")

        desc_outra_desp = st.text_input("Observação / Descrição de outro custo (Opcional):", placeholder="Ex: Troca de palheta, refeição...")

        btn_concluir_turno = st.form_submit_button("🏁 Concluir Fechamento do Turno", type="primary", use_container_width=True)

        if btn_concluir_turno:
            k_ini_parsed = converter_km(txt_kmi)
            k_fim_parsed = converter_km(txt_kmf)

            if k_fim_parsed is not None and k_ini_parsed is not None:
                if k_fim_parsed < k_ini_parsed:
                    st.error("O KM final não pode ser menor que o KM inicial.")
                    st.stop()
                k_rod_calc = k_fim_parsed - k_ini_parsed
            else:
                k_rod_calc = None

            # Monta lista de lançamentos preenchidos
            itens_para_gravar = []
            mapa_receitas = [
                ("Uber sem pedágios", v_uber),
                ("99 com pedágios", v_99),
                ("Pedágio Uber", v_ped_uber),
                ("Particular", v_part),
            ]
            for cat, campo in mapa_receitas:
                val = converter_valor(campo)
                if val > 0:
                    itens_para_gravar.append({"tipo": "Receita", "categoria": cat, "descricao": "", "valor": val})

            mapa_despesas = [
                ("Combustível", v_combustivel, ""),
                ("SemParar do dia", v_semparar, ""),
                ("Lavagem", v_lavagem, ""),
            ]
            for cat, campo, obs in mapa_despesas:
                val = converter_valor(campo)
                if val > 0:
                    itens_para_gravar.append({"tipo": "Despesa", "categoria": cat, "descricao": obs, "valor": val})

            val_outra = converter_valor(v_outra_desp)
            if val_outra > 0:
                itens_para_gravar.append({"tipo": "Despesa", "categoria": "Outro", "descricao": desc_outra_desp.strip(), "valor": val_outra})

            if not itens_para_gravar and k_rod_calc is None:
                st.warning("Preencha ao menos a quilometragem ou um valor financeiro.")
            else:
                salvar_fechamento_turno(data_atual, k_ini_parsed, k_fim_parsed, k_rod_calc, itens_para_gravar)
                st.session_state["msg_sucesso"] = f"Turno de {data_atual.strftime('%d/%m/%Y')} fechado com sucesso!"
                st.rerun()

# ==========================================
# ABA 2: GERENCIAR REGISTROS
# ==========================================
with tab_gerenciar:
    if df_completo.empty:
        st.info("Nenhum lançamento financeiro registrado.")
    else:
        busca = st.text_input("🔍 Pesquisar lançamentos:", placeholder="Filtre por categoria ou observação...").lower().strip()
        df_lista = df_completo.copy()
        if busca:
            df_lista = df_lista[
                df_lista["categoria"].str.lower().str.contains(busca, na=False) |
                df_lista["descricao"].str.lower().str.contains(busca, na=False)
            ]

        st.caption(f"Exibindo {min(len(df_lista), 40)} de {len(df_lista)} lançamentos")

        for _, row in df_lista.head(40).iterrows():
            item_id = int(row["id"])
            item_data = row["data"].date()
            val_formatado = formata_real(row["valor"])
            tipo_icon = "🟢" if row["tipo"] == "Receita" else "🔴"
            obs = f" - *{row['descricao']}*" if row["descricao"] else ""

            col_info, col_b1, col_b2 = st.columns([5, 1.2, 1.2])
            with col_info:
                st.markdown(f"{tipo_icon} **{item_data.strftime('%d/%m/%Y')}** | **{row['categoria']}** | **{val_formatado}**{obs} `(ID: {item_id})`")
            with col_b1:
                if st.button("✏️", key=f"btn_edit_{item_id}", use_container_width=True):
                    modal_editar_registro(item_id, item_data, row["tipo"], row["categoria"], row["descricao"], row["valor"])
            with col_b2:
                if st.button("🗑️", key=f"btn_del_{item_id}", use_container_width=True):
                    modal_excluir_registro(item_id, row["categoria"], val_formatado)

st.markdown("---")

# ==========================================
# PAINEL ANALÍTICO & RELATÓRIOS
# ==========================================
st.subheader("📊 Indicadores de Performance Operacional")

opcoes_periodo = [
    "Hoje", "Ontem", "Últimos 7 dias", "Últimos 30 dias", 
    "Semanal", "Mensal", "Anual", "Tudo", "Personalizado"
]

if hasattr(st, "pills"):
    periodo_selecionado = st.pills("Período:", opcoes_periodo, default="Hoje")
else:
    periodo_selecionado = st.radio("Período:", opcoes_periodo, horizontal=True)

hoje = obter_data_hoje()

if periodo_selecionado == "Hoje":
    d_inicio = hoje
    d_fim = hoje
elif periodo_selecionado == "Ontem":
    d_inicio = hoje - timedelta(days=1)
    d_fim = hoje - timedelta(days=1)
elif periodo_selecionado == "Últimos 7 dias":
    d_inicio = hoje - timedelta(days=6)
    d_fim = hoje
elif periodo_selecionado == "Últimos 30 dias":
    d_inicio = hoje - timedelta(days=29)
    d_fim = hoje
elif periodo_selecionado == "Semanal":
    d_inicio = hoje - timedelta(days=hoje.weekday())
    d_fim = d_inicio + timedelta(days=6)
elif periodo_selecionado == "Mensal":
    d_inicio = date(hoje.year, hoje.month, 1)
    proximo_mes = date(hoje.year + 1, 1, 1) if hoje.month == 12 else date(hoje.year, hoje.month + 1, 1)
    d_fim = proximo_mes - timedelta(days=1)
elif periodo_selecionado == "Anual":
    d_inicio = date(hoje.year, 1, 1)
    d_fim = date(hoje.year, 12, 31)
elif periodo_selecionado == "Tudo":
    d_inicio = df_completo["data"].min().date() if not df_completo.empty else hoje
    d_fim = df_completo["data"].max().date() if not df_completo.empty else hoje
else:
    min_base = df_completo["data"].min().date() if not df_completo.empty else hoje
    max_base = df_completo["data"].max().date() if not df_completo.empty else hoje
    intervalo = st.date_input("Datas:", value=(min_base, max_base))
    if isinstance(intervalo, (list, tuple)) and len(intervalo) == 2:
        d_inicio, d_fim = intervalo
    else:
        d_inicio, d_fim = min_base, max_base

# Filtro de registros financeiros e de quilometragem
df_f = df_completo[(df_completo["data"].dt.date >= d_inicio) & (df_completo["data"].dt.date <= d_fim)].copy()
df_km_f = df_turnos_km[(df_turnos_km["data"].dt.date >= d_inicio) & (df_turnos_km["data"].dt.date <= d_fim)].copy()

tot_rec = df_f[df_f["tipo"] == "Receita"]["valor"].sum() if not df_f.empty else 0.0
tot_desp = df_f[df_f["tipo"] == "Despesa"]["valor"].sum() if not df_f.empty else 0.0
lucro = tot_rec - tot_desp
margem = (lucro / tot_rec * 100) if tot_rec > 0 else 0.0

tot_km = df_km_f["km_rodado"].dropna().sum() if not df_km_f.empty else 0.0
rec_km = (tot_rec / tot_km) if tot_km > 0 else 0.0
custo_km = (tot_desp / tot_km) if tot_km > 0 else 0.0
lucro_km = (lucro / tot_km) if tot_km > 0 else 0.0

# 1. CARDS DE RESULTADOS FINANCEIROS
k1, k2, k3 = st.columns(3)
k1.metric("Faturamento Bruto", formata_real(tot_rec))
k2.metric("Despesas Totais", formata_real(tot_desp))
k3.metric("Lucro Líquido", formata_real(lucro), delta=f"{margem:.1f}% margem")

# 2. CARDS DE EFICIÊNCIA DE QUILOMETRAGEM
m1, m2, m3, m4 = st.columns(4)
m1.metric("🚗 KM Rodados", f"{tot_km:.1f} km" if tot_km > 0 else "0 km")
m2.metric("💰 R$/KM Faturado", formata_real(rec_km))
m3.metric("⛽ Custo/KM", formata_real(custo_km))
m4.metric("📈 Lucro Líquido/KM", formata_real(lucro_km))

# --- TABELA DE LANÇAMENTOS DO PERÍODO ---
st.markdown("---")
st.markdown("#### 📋 Lançamentos Detalhados")

if not df_f.empty:
    outras_rec = df_f[(df_f["tipo"] == "Receita") & (~df_f["categoria"].isin(OPCOES_RECEITA_FIXAS))]["categoria"].unique().tolist()
    outras_desp = df_f[(df_f["tipo"] == "Despesa") & (~df_f["categoria"].isin(OPCOES_DESPESA_FIXAS))]["categoria"].unique().tolist()

    opcoes_filtro = [c for c in OPCOES_RECEITA_FIXAS if c in df_f["categoria"].values]
    if outras_rec:
        opcoes_filtro.append("Outras receitas")
    opcoes_filtro += [c for c in OPCOES_DESPESA_FIXAS if c in df_f["categoria"].values]
    if outras_desp:
        opcoes_filtro.append("Outras despesas")

    cats_selecionadas = st.multiselect(
        "Filtrar por Categoria:",
        options=opcoes_filtro,
        default=opcoes_filtro,
        placeholder="Selecione as categorias para apuração..."
    )

    cats_ativas = []
    for s in cats_selecionadas:
        if s == "Outras receitas":
            cats_ativas.extend(outras_rec)
        elif s == "Outras despesas":
            cats_ativas.extend(outras_desp)
        else:
            cats_ativas.append(s)

    df_tab = df_f[df_f["categoria"].isin(set(cats_ativas))].copy()

    if not df_tab.empty:
        df_tab["data_formatada"] = df_tab["data"].dt.strftime("%d/%m/%Y")
        df_tab["valor_formatado"] = df_tab["valor"].apply(lambda v: formata_real(v))

        st.dataframe(
            df_tab[["id", "data_formatada", "tipo", "categoria", "valor_formatado", "descricao"]],
            column_config={
                "id": st.column_config.NumberColumn("ID", width="small"),
                "data_formatada": st.column_config.TextColumn("Data", width="small"),
                "tipo": st.column_config.TextColumn("Tipo", width="small"),
                "categoria": st.column_config.TextColumn("Categoria", width="medium"),
                "valor_formatado": st.column_config.TextColumn("Valor", width="small"),
                "descricao": st.column_config.TextColumn("Observação", width="large")
            },
            use_container_width=True,
            hide_index=True
        )

        col_exp1, col_exp2 = st.columns(2)
        with col_exp1:
            csv_data = df_tab[["id", "data", "tipo", "categoria", "valor", "descricao"]].to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Baixar Dados da Tabela (CSV)",
                data=csv_data,
                file_name=f"financeiro_{periodo_selecionado.lower().replace(' ', '_')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        with col_exp2:
            dossie_txt = gerar_dossie_ia(df_f, df_km_f, d_inicio, d_fim)
            st.download_button(
                label="🤖 Baixar Dossiê Completo para IA (.md)",
                data=dossie_txt.encode('utf-8'),
                file_name=f"dossie_ia_motorista_{periodo_selecionado.lower().replace(' ', '_')}.md",
                mime="text/markdown",
                type="primary",
                use_container_width=True
            )
else:
    st.info("Nenhum lançamento no período selecionado.")

# --- GRÁFICOS: PIZZAS PRIMEIRO, BARRAS NO FINAL ---
if not df_f.empty:
    st.markdown("---")
    st.markdown("#### 📊 Distribuição por Origem e Custo")
    col_p1, col_p2 = st.columns(2)

    df_rec = df_f[df_f["tipo"] == "Receita"]
    df_desp = df_f[df_f["tipo"] == "Despesa"]

    with col_p1:
        if not df_rec.empty:
            fig_p_rec = px.pie(df_rec, names="categoria", values="valor", title="Origem dos Ganhos", hole=0.45)
            fig_p_rec.update_traces(textposition='inside', textinfo='percent+label')
            fig_p_rec.update_layout(showlegend=False, margin=dict(l=10, r=10, t=35, b=10))
            st.plotly_chart(fig_p_rec, use_container_width=True, config={"displayModeBar": False})
    with col_p2:
        if not df_desp.empty:
            fig_p_desp = px.pie(df_desp, names="categoria", values="valor", title="Composição dos Custos", hole=0.45)
            fig_p_desp.update_traces(textposition='inside', textinfo='percent+label')
            fig_p_desp.update_layout(showlegend=False, margin=dict(l=10, r=10, t=35, b=10))
            st.plotly_chart(fig_p_desp, use_container_width=True, config={"displayModeBar": False})

    st.markdown("#### 📈 Evolução no Período")
    delta_dias = (d_fim - d_inicio).days
    df_f["agrup"] = df_f["data"].dt.strftime("%d/%m") if delta_dias <= 31 else df_f["data"].dt.strftime("%m/%Y")
    df_agrup = df_f.groupby(["agrup", "tipo"], sort=False)["valor"].sum().reset_index()

    fig_bar = px.bar(
        df_agrup, x="agrup", y="valor", color="tipo", barmode="group",
        labels={"agrup": "Data", "valor": "R$", "tipo": "Tipo"},
        color_discrete_map={"Receita": "#00CC96", "Despesa": "#EF553B"}
    )
    fig_bar.update_layout(
        margin=dict(l=10, r=10, t=15, b=25),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis_title=None,
        dragmode=False,
        xaxis=dict(fixedrange=True),
        yaxis=dict(fixedrange=True)
    )
    st.plotly_chart(fig_bar, use_container_width=True, config={"scrollZoom": False, "displayModeBar": False})

# Bloqueio de teclado em inputs de data
components.html("""
<script>
    function travarTecladoData() {
        const doc = window.parent.document;
        const inputs = doc.querySelectorAll('div[data-testid="stDateInput"] input');
        inputs.forEach(input => {
            input.setAttribute('inputmode', 'none');
            input.setAttribute('readonly', 'true');
            input.onfocus = function() { input.blur(); };
        });
    }
    travarTecladoData();
    const obs = new MutationObserver(travarTecladoData);
    obs.observe(window.parent.document.body, { childList: true, subtree: true });
</script>
""", height=0, width=0)
