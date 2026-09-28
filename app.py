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
    .card-fechamento-km {
        padding: 14px 18px;
        border-radius: 10px;
        background-color: rgba(0, 204, 150, 0.08);
        border: 1px solid rgba(0, 204, 150, 0.3);
        margin-bottom: 12px;
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

# Nomenclaturas fixas
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

def formata_km(valor):
    if pd.isnull(valor) or valor is None:
        return "0 km"
    return f"{int(round(valor)):,}".replace(",", ".") + " km"

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

def converter_km_inteiro(texto):
    if not texto:
        return None
    texto_limpo = str(texto).strip().replace(".", "").replace(",", "").replace("km", "").replace("KM", "").strip()
    try:
        val = int(texto_limpo)
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

# Inicialização e Migração Automática de Tabelas
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
                    data DATE NOT NULL,
                    km_inicial INTEGER,
                    km_final INTEGER,
                    km_rodado INTEGER
                );
            '''))
            conn.execute(text('''
                ALTER TABLE turnos_km ADD COLUMN IF NOT EXISTS id SERIAL;
            '''))
            conn.execute(text('''
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM pg_constraint 
                        WHERE conname = 'turnos_km_pkey'
                    ) THEN
                        ALTER TABLE turnos_km DROP CONSTRAINT turnos_km_pkey;
                    END IF;
                END $$;
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
    else:
        df = pd.DataFrame(columns=["id", "data", "tipo", "categoria", "descricao", "valor"])
        df["data"] = pd.to_datetime(df["data"])
        df["valor"] = df["valor"].astype(float)
    return df

@st.cache_data(ttl=600)
def carregar_turnos_km():
    with engine.connect() as conn:
        df_km = pd.read_sql_query(text("SELECT * FROM turnos_km ORDER BY data DESC, id ASC"), conn)
    
    if not df_km.empty:
        df_km["data"] = pd.to_datetime(df_km["data"])
        df_km["km_inicial"] = pd.to_numeric(df_km["km_inicial"], errors="coerce")
        df_km["km_final"] = pd.to_numeric(df_km["km_final"], errors="coerce")
        df_km["km_rodado"] = pd.to_numeric(df_km["km_rodado"], errors="coerce")
    else:
        df_km = pd.DataFrame(columns=["id", "data", "km_inicial", "km_final", "km_rodado"])
        df_km["data"] = pd.to_datetime(df_km["data"])
    return df_km

def abrir_novo_turno(data_reg, km_ini):
    with engine.begin() as conn:
        conn.execute(text('''
            INSERT INTO turnos_km (data, km_inicial)
            VALUES (:data, :km_inicial);
        '''), {"data": data_reg, "km_inicial": km_ini})
    carregar_turnos_km.clear()

def fechar_turno(turno_id, km_fim, km_rodado):
    with engine.begin() as conn:
        conn.execute(text('''
            UPDATE turnos_km
            SET km_final = :km_fim, km_rodado = :km_rodado
            WHERE id = :id;
        '''), {"km_fim": km_fim, "km_rodado": km_rodado, "id": turno_id})
    carregar_turnos_km.clear()

def editar_turno_banco(turno_id, km_ini, km_fim):
    km_rod = (km_fim - km_ini) if (km_fim is not None and km_fim >= km_ini) else None
    with engine.begin() as conn:
        conn.execute(text('''
            UPDATE turnos_km
            SET km_inicial = :km_ini, km_final = :km_fim, km_rodado = :km_rod
            WHERE id = :id;
        '''), {"km_ini": km_ini, "km_fim": km_fim, "km_rod": km_rod, "id": turno_id})
    carregar_turnos_km.clear()

def deletar_turno_banco(turno_id):
    with engine.begin() as conn:
        conn.execute(text('DELETE FROM turnos_km WHERE id = :id'), {"id": turno_id})
    carregar_turnos_km.clear()

def inserir_registro_avulso(data_reg, tipo, categoria, descricao, valor):
    with engine.begin() as conn:
        conn.execute(text('''
            INSERT INTO lancamentos (data, tipo, categoria, descricao, valor)
            VALUES (:data, :tipo, :categoria, :descricao, :valor)
        '''), {"data": data_reg, "tipo": tipo, "categoria": categoria, "descricao": descricao, "valor": valor})
    carregar_dados.clear()

def salvar_fechamento_em_lote(data_reg, lista_lancamentos):
    with engine.begin() as conn:
        for item in lista_lancamentos:
            conn.execute(text('''
                INSERT INTO lancamentos (data, tipo, categoria, descricao, valor)
                VALUES (:data, :tipo, :categoria, :descricao, :valor)
            '''), {
                "data": data_reg,
                "tipo": item["tipo"],
                "categoria": item["categoria"],
                "descricao": item["descricao"],
                "valor": item["valor"]
            })
    carregar_dados.clear()

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

# Gerador de Dossiê para IA
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

    tot_km = int(round(df_km_periodo["km_rodado"].dropna().sum())) if not df_km_periodo.empty else 0
    rec_por_km = (tot_rec / tot_km) if tot_km > 0 else 0.0
    custo_por_km = (tot_desp / tot_km) if tot_km > 0 else 0.0
    lucro_por_km = (lucro / tot_km) if tot_km > 0 else 0.0

    dias_trabalhados = df_local["data"].dt.date.nunique() if not df_local.empty else df_km_periodo["data"].dt.date.nunique()
    media_lucro_dia = (lucro / dias_trabalhados) if dias_trabalhados > 0 else 0.0
    media_km_dia = (tot_km / dias_trabalhados) if dias_trabalhados > 0 else 0

    rec_por_cat = df_local[df_local["tipo"] == "Receita"].groupby("categoria")["valor"].sum().to_dict() if not df_local.empty else {}
    desp_por_cat = df_local[df_local["tipo"] == "Despesa"].groupby("categoria")["valor"].sum().to_dict() if not df_local.empty else {}

    prompt_linhas = [
        "# RELATÓRIO OPERACIONAL E FINANCEIRO — MOTORISTA DE APLICATIVO",
        "",
        "## INSTRUÇÕES PARA A INTELIGÊNCIA ARTIFICIAL",
        "Você é um consultor financeiro e de estratégia operacional para motoristas de aplicativo.",
        "Analise os dados financeiros e MÉTRICAS DE QUILOMETRAGEM (R$/km, Custo/km e Lucro/km) para apontar como aumentar o lucro.",
        "Nota: O motorista registra múltiplos turnos por dia, descartando KMs de uso particular entre as pausas.",
        "",
        "### REGRAS CONTÁBEIS IMPORTANTES:",
        "- **99 com pedágios:** Já embute o reembolso dos pedágios.",
        "- **Uber sem pedágios:** Não inclui pedágios (estes estão sob 'Pedágio Uber').",
        "- **SemParar do dia / Pedágios:** Custo real pago pelo motorista. Não deduza pedágios duas vezes.",
        "",
        "---",
        "## 1. RESUMO EXECUTIVO DO PERÍODO",
        f"- **Período:** {d_ini.strftime('%d/%m/%Y')} até {d_end.strftime('%d/%m/%Y')}",
        f"- **Dias Trabalhados:** {dias_trabalhados} dia(s)",
        f"- **Quilometragem Total Trabalhada:** {formata_km(tot_km)} (Média: {formata_km(media_km_dia)}/dia)",
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

    return "\n".join(prompt_linhas)

# Carregamento de dados
df_completo = carregar_dados()
df_turnos_km = carregar_turnos_km()

if "msg_sucesso" in st.session_state:
    st.success(st.session_state.pop("msg_sucesso"))

# Estado da data
if "data_operacao" not in st.session_state:
    st.session_state["data_operacao"] = obter_data_hoje()

if "date_ver" not in st.session_state:
    st.session_state["date_ver"] = 0

# Modal de Edição de Turno
@st.dialog("✏️ Editar Turno de KM")
def modal_editar_turno(turno_id, km_ini_atual, km_fim_atual):
    st.write(f"Editar Odômetros do **Turno #{turno_id}**:")
    txt_ini = st.text_input("KM Inicial:", value=str(int(km_ini_atual)) if km_ini_atual else "")
    txt_fim = st.text_input("KM Final (opcional):", value=str(int(km_fim_atual)) if km_fim_atual else "")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Salvar Turno", type="primary", use_container_width=True):
            p_ini = converter_km_inteiro(txt_ini)
            p_fim = converter_km_inteiro(txt_fim)
            if p_ini is None or p_ini <= 0:
                st.error("Informe um KM inicial válido.")
            elif p_fim is not None and p_fim < p_ini:
                st.error("O KM final não pode ser menor que o inicial.")
            else:
                editar_turno_banco(turno_id, p_ini, p_fim)
                st.session_state["msg_sucesso"] = "Turno atualizado com sucesso!"
                st.rerun()
    with col2:
        if st.button("✖️ Cancelar", use_container_width=True):
            st.rerun()

# Modal de Edição de Lançamento Financeiro
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
tab_operacao, tab_gerenciar = st.tabs(["⚡ Operação do Dia (Turnos & Parciais)", "⚙️ Histórico Financeiro"])

# ==============================================================
# ABA 1: OPERAÇÃO DO DIA (TURNOS, PARCIAIS E FECHAMENTO GERAL)
# ==============================================================
with tab_operacao:
    # Seletor de Data
    st.markdown("**Data de Trabalho:**")
    c_h, c_o, c_d = st.columns([1, 1, 2])
    with c_h:
        if st.button("📅 Hoje", use_container_width=True):
            st.session_state["data_operacao"] = obter_data_hoje()
            st.session_state["date_ver"] += 1
            st.rerun()
    with c_o:
        if st.button("📅 Ontem", use_container_width=True):
            st.session_state["data_operacao"] = obter_data_hoje() - timedelta(days=1)
            st.session_state["date_ver"] += 1
            st.rerun()
    with c_d:
        dt_sel = st.date_input(
            "Data",
            value=st.session_state["data_operacao"],
            key=f"data_sel_op_{st.session_state['date_ver']}",
            label_visibility="collapsed"
        )
        st.session_state["data_operacao"] = dt_sel

    data_atual = st.session_state["data_operacao"]
    st.caption(f"🗓️ Gerenciando dia: **{data_atual.strftime('%d/%m/%Y')}** ({DIAS_SEMANA_PT[data_atual.weekday()]})")

    # Filtra turnos e lançamentos do dia selecionado
    turnos_do_dia = df_turnos_km[df_turnos_km["data"].dt.date == data_atual].sort_values("id") if not df_turnos_km.empty else pd.DataFrame()
    turno_aberto = turnos_do_dia[turnos_do_dia["km_final"].isnull()] if not turnos_do_dia.empty else pd.DataFrame()
    tem_turno_aberto = not turno_aberto.empty
    total_km_dia = int(round(turnos_do_dia["km_rodado"].dropna().sum())) if not turnos_do_dia.empty else 0

    # Lançamentos já realizados hoje
    lancamentos_hoje = df_completo[df_completo["data"].dt.date == data_atual] if not df_completo.empty else pd.DataFrame()

    # --- SEÇÃO 1: GESTÃO DE TURNOS DE QUILOMETRAGEM ---
    st.markdown("---")
    st.markdown("#### 🚗 1. Turnos de Trabalho (Quilometragem)")
    st.caption("Abra um turno ao começar a trabalhar e feche ao pausar para atividades particulares.")

    if not turnos_do_dia.empty:
        st.markdown(f"**Turnos de trabalho no dia:** (Soma acumulada: **{formata_km(total_km_dia)}**)")
        idx_t = 1
        for _, t in turnos_do_dia.iterrows():
            t_id = int(t["id"])
            k_ini = int(t["km_inicial"])
            k_fim = int(t["km_final"]) if pd.notnull(t["km_final"]) else None
            k_rod = int(t["km_rodado"]) if pd.notnull(t["km_rodado"]) else None

            col_t_info, col_t_edit, col_t_del = st.columns([5, 1, 1])
            with col_t_info:
                if k_fim is not None:
                    st.markdown(f"✅ **Turno {idx_t}:** {k_ini:,} km ➔ {k_fim:,} km | **+{k_rod} km rodados**".replace(",", "."))
                else:
                    st.markdown(f"⏳ **Turno {idx_t} (EM ANDAMENTO):** Aberto em **{k_ini:,} km**".replace(",", "."))
            with col_t_edit:
                if st.button("✏️", key=f"btn_ed_turno_{t_id}", use_container_width=True):
                    modal_editar_turno(t_id, k_ini, k_fim)
            with col_t_del:
                if st.button("🗑️", key=f"btn_del_turno_{t_id}", use_container_width=True):
                    deletar_turno_banco(t_id)
                    st.session_state["msg_sucesso"] = f"Turno #{t_id} removido."
                    st.rerun()
            idx_t += 1

    # Form de Abrir/Fechar Turno
    if tem_turno_aberto:
        t_ativo = turno_aberto.iloc[0]
        id_aberto = int(t_ativo["id"])
        km_ini_ativo = int(t_ativo["km_inicial"])

        st.warning(f"🔔 **Turno em Aberto:** Iniciado em **{km_ini_ativo:,} km**.".replace(",", "."))
        with st.form("form_fechar_turno"):
            c_kf, c_btnf = st.columns([2, 1])
            with c_kf:
                input_km_fim = st.text_input("Odômetro ao encerrar este turno:", placeholder=f"Ex: {km_ini_ativo + 80}")
            with c_btnf:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                btn_fechar_t = st.form_submit_button("🏁 Pausar / Fechar Turno", type="primary", use_container_width=True)

            if btn_fechar_t:
                val_kf = converter_km_inteiro(input_km_fim)
                if val_kf is None or val_kf <= 0:
                    st.error("Digite um KM final válido.")
                elif val_kf < km_ini_ativo:
                    st.error(f"O KM final não pode ser menor que o inicial ({km_ini_ativo:,} km).".replace(",", "."))
                else:
                    km_rodado_calc = val_kf - km_ini_ativo
                    fechar_turno(id_aberto, val_kf, km_rodado_calc)
                    st.session_state["msg_sucesso"] = f"Turno finalizado! +{km_rodado_calc} km computados."
                    st.rerun()
    else:
        with st.form("form_abrir_turno"):
            c_ki, c_btni = st.columns([2, 1])
            with c_ki:
                ultimo_km = int(turnos_do_dia["km_final"].dropna().iloc[-1]) if not turnos_do_dia.empty and not turnos_do_dia["km_final"].dropna().empty else ""
                placeholder_sug = f"Ex: {ultimo_km}" if ultimo_km else "Ex: 85420"
                input_km_ini = st.text_input("Odômetro ao começar este turno:", value=str(ultimo_km) if ultimo_km else "", placeholder=placeholder_sug)
            with c_btni:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                btn_abrir_t = st.form_submit_button("🟢 Iniciar Novo Turno", type="primary", use_container_width=True)

            if btn_abrir_t:
                val_ki = converter_km_inteiro(input_km_ini)
                if val_ki is None or val_ki <= 0:
                    st.error("Informe um KM inicial inteiro e válido.")
                else:
                    abrir_novo_turno(data_atual, val_ki)
                    st.session_state["msg_sucesso"] = f"Turno iniciado em {val_ki:,} km!".replace(",", ".")
                    st.rerun()

    # --- SEÇÃO 2: LANÇAMENTO RÁPIDO PARCIAL AO LONGO DO DIA ---
    st.markdown("---")
    st.markdown("#### ⚡ 2. Lançamento Rápido no Dia (Despesas ou Ganhos)")
    st.caption("Abasteceu, lavou o carro ou recebeu uma corrida avulsa? Salve aqui imediatamente a qualquer momento.")

    col_sel_tipo, col_sel_cat = st.columns(2)
    with col_sel_tipo:
        tipo_avulso = st.radio("Tipo:", ["Despesa (Custos)", "Receita (Ganhos)"], horizontal=True, key="rad_tipo_avulso")
    
    eh_rec = tipo_avulso == "Receita (Ganhos)"
    opcoes_atuais = OPCOES_RECEITA_FORM if eh_rec else OPCOES_DESPESA_FORM

    with col_sel_cat:
        cat_avulsa_sel = st.selectbox("Categoria:", opcoes_atuais, key="box_cat_avulsa")

    with st.form("form_lancamento_parcial", clear_on_submit=True):
        cat_final_avulsa = cat_avulsa_sel
        if cat_avulsa_sel == "Outro":
            cat_espec = st.text_input("Especifique a categoria *", placeholder="Ex: Estacionamento, Lanche, Óleo...")
            cat_final_avulsa = cat_espec.strip()

        col_val_a, col_obs_a = st.columns([1.2, 2])
        with col_val_a:
            val_avulso_str = st.text_input("Valor (R$):", placeholder="Ex: 50,00 ou 15,50")
        with col_obs_a:
            obs_avulsa = st.text_input("Observação (Opcional):", placeholder="Ex: Posto Shell, Lavagem completa...")

        btn_salvar_parcial = st.form_submit_button("💾 Salvar Registro Parcial", type="primary", use_container_width=True)

        if btn_salvar_parcial:
            v_calc = converter_valor(val_avulso_str)
            if v_calc <= 0:
                st.error("Informe um valor maior que zero.")
            elif cat_avulsa_sel == "Outro" and not cat_final_avulsa:
                st.error("Indique o nome da categoria 'Outro'.")
            else:
                tipo_bd = "Receita" if eh_rec else "Despesa"
                inserir_registro_avulso(data_atual, tipo_bd, cat_final_avulsa, obs_avulsa.strip(), v_calc)
                st.session_state["msg_sucesso"] = f"{tipo_bd} de {formata_real(v_calc)} salva com sucesso!"
                st.rerun()

    # --- SEÇÃO 3: FECHAMENTO GERAL DO DIA (CHECKLIST CONSOLIDADO) ---
    st.markdown("---")
    st.markdown("#### 🏁 3. Fechamento Geral do Dia (Checklist Final)")
    st.caption("Consolide o encerramento do seu dia: veja os KMs totais, itens já salvos e lance o que ficou pendente.")

    # Card com a soma total dos KMs de todos os turnos de trabalho
    col_km_soma1, col_km_soma2 = st.columns([2.5, 1])
    with col_km_soma1:
        st.markdown(f"**🚗 Quilometragem Total Trabalhada no Dia:**")
        st.markdown(f"### `{formata_km(total_km_dia)}`")
    with col_km_soma2:
        if tem_turno_aberto:
            st.error("⚠️ Há um turno aberto!")
        else:
            qtd_turnos = len(turnos_do_dia)
            st.success(f"✔️ {qtd_turnos} turno(s) fechado(s)")

    # Mapeamento do que já foi lançado hoje
    categorias_lancadas_hoje = {}
    if not lancamentos_hoje.empty:
        for _, row in lancamentos_hoje.iterrows():
            categorias_lancadas_hoje[row["categoria"]] = {
                "id": int(row["id"]),
                "tipo": row["tipo"],
                "valor": float(row["valor"]),
                "descricao": row["descricao"] if row["descricao"] else ""
            }

    # Formulário do Fechamento do Dia
    with st.form("form_fechamento_geral_dia"):
        st.markdown("##### 🟢 Ganhos (Receitas do Dia):")
        
        campos_pendentes_rec = {}
        for cat in OPCOES_RECEITA_FIXAS:
            if cat in categorias_lancadas_hoje:
                dados_cat = categorias_lancadas_hoje[cat]
                st.text_input(
                    f"✔️ {cat} (Já Registrado - Travado):",
                    value=f"{formata_real(dados_cat['valor'])} - {dados_cat['descricao']}" if dados_cat['descricao'] else formata_real(dados_cat['valor']),
                    disabled=True,
                    key=f"lock_rec_{cat}"
                )
            else:
                campos_pendentes_rec[cat] = st.text_input(
                    f"{cat} (R$):",
                    placeholder="Deixe em branco se não realizou",
                    key=f"pend_rec_{cat}"
                )

        st.markdown("---")
        st.markdown("##### 🔴 Despesas do Dia:")
        
        campos_pendentes_desp = {}
        for cat in OPCOES_DESPESA_FIXAS:
            if cat in categorias_lancadas_hoje:
                dados_cat = categorias_lancadas_hoje[cat]
                st.text_input(
                    f"✔️ {cat} (Já Registrado - Travado):",
                    value=f"{formata_real(dados_cat['valor'])} - {dados_cat['descricao']}" if dados_cat['descricao'] else formata_real(dados_cat['valor']),
                    disabled=True,
                    key=f"lock_desp_{cat}"
                )
            else:
                campos_pendentes_desp[cat] = st.text_input(
                    f"{cat} (R$):",
                    placeholder="Deixe em branco se não gastou",
                    key=f"pend_desp_{cat}"
                )

        st.markdown("---")
        st.markdown("##### ➕ Outro Custo / Manutenção Adicional:")
        col_out1, col_out2 = st.columns([1.2, 2])
        with col_out1:
            val_outro_fechamento = st.text_input("Outro Custo (R$):", placeholder="0,00", key="fech_outro_val")
        with col_out2:
            obs_outro_fechamento = st.text_input("Observação do outro custo:", placeholder="Ex: Troca de lâmpada, café...", key="fech_outro_obs")

        btn_concluir_dia = st.form_submit_button("🏁 Gravar Fechamento Final do Dia", type="primary", use_container_width=True)

        if btn_concluir_dia:
            novos_itens = []

            # Coleta receitas pendentes preenchidas
            for cat, campo_val in campos_pendentes_rec.items():
                v = converter_valor(campo_val)
                if v > 0:
                    novos_itens.append({"tipo": "Receita", "categoria": cat, "descricao": "", "valor": v})

            # Coleta despesas pendentes preenchidas
            for cat, campo_val in campos_pendentes_desp.items():
                v = converter_valor(campo_val)
                if v > 0:
                    novos_itens.append({"tipo": "Despesa", "categoria": cat, "descricao": "", "valor": v})

            # Coleta outro custo se informado
            v_outro = converter_valor(val_outro_fechamento)
            if v_outro > 0:
                novos_itens.append({"tipo": "Despesa", "categoria": "Outro", "descricao": obs_outro_fechamento.strip(), "valor": v_outro})

            if not novos_itens and not categorias_lancadas_hoje and total_km_dia == 0:
                st.warning("Preencha ao menos uma categoria pendente para concluir o fechamento.")
            else:
                if novos_itens:
                    salvar_fechamento_em_lote(data_atual, novos_itens)
                st.session_state["msg_sucesso"] = f"Fechamento do dia {data_atual.strftime('%d/%m/%Y')} concluído com sucesso!"
                st.rerun()

    # Painel de Lançamentos de Hoje com botão de edição rápida dos itens já salvos
    if not lancamentos_hoje.empty:
        st.markdown(f"**Itens já lançados hoje:** *(clique em ✏️ se precisar alterar algum valor)*")
        for _, row in lancamentos_hoje.iterrows():
            item_id = int(row["id"])
            t_icon = "🟢" if row["tipo"] == "Receita" else "🔴"
            obs_txt = f" - *{row['descricao']}*" if row["descricao"] else ""

            col_inf_hoje, col_btn_hoje = st.columns([5, 1])
            with col_inf_hoje:
                st.markdown(f"{t_icon} **{row['categoria']}**: **{formata_real(row['valor'])}**{obs_txt}")
            with col_btn_hoje:
                if st.button("✏️ Editar", key=f"btn_ed_hoje_{item_id}", use_container_width=True):
                    modal_editar_registro(item_id, data_atual, row["tipo"], row["categoria"], row["descricao"], row["valor"])

# ==============================================================
# ABA 2: GERENCIAR REGISTROS (HISTÓRICO FINANCEIRO)
# ==============================================================
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

# ==============================================================
# PAINEL ANALÍTICO & RELATÓRIOS CONSOLIDADOS
# ==============================================================
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

# Filtro dos lançamentos financeiros e de KM
if not df_completo.empty:
    df_f = df_completo[(df_completo["data"].dt.date >= d_inicio) & (df_completo["data"].dt.date <= d_fim)].copy()
else:
    df_f = pd.DataFrame(columns=["id", "data", "tipo", "categoria", "descricao", "valor"])

if not df_turnos_km.empty:
    df_km_f = df_turnos_km[(df_turnos_km["data"].dt.date >= d_inicio) & (df_turnos_km["data"].dt.date <= d_fim)].copy()
else:
    df_km_f = pd.DataFrame(columns=["id", "data", "km_inicial", "km_final", "km_rodado"])

tot_rec = df_f[df_f["tipo"] == "Receita"]["valor"].sum() if not df_f.empty else 0.0
tot_desp = df_f[df_f["tipo"] == "Despesa"]["valor"].sum() if not df_f.empty else 0.0
lucro = tot_rec - tot_desp
margem = (lucro / tot_rec * 100) if tot_rec > 0 else 0.0

tot_km = int(round(df_km_f["km_rodado"].dropna().sum())) if not df_km_f.empty else 0
rec_km = (tot_rec / tot_km) if tot_km > 0 else 0.0
custo_km = (tot_desp / tot_km) if tot_km > 0 else 0.0
lucro_km = (lucro / tot_km) if tot_km > 0 else 0.0

# 1. CARDS DE RESULTADOS FINANCEIROS
k1, k2, k3 = st.columns(3)
k1.metric("Faturamento Bruto", formata_real(tot_rec))
k2.metric("Despesas Totais", formata_real(tot_desp))
k3.metric("Lucro Líquido", formata_real(lucro), delta=f"{margem:.1f}% margem")

# 2. CARDS DE EFICIÊNCIA DE QUILOMETRAGEM (SOMENTE TURNOS DE TRABALHO)
m1, m2, m3, m4 = st.columns(4)
m1.metric("🚗 KM Trabalhados", formata_km(tot_km))
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
    st.info("Nenhum lançamento financeiro no período selecionado.")

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
