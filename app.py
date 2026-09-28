import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import plotly.express as px
from sqlalchemy import create_engine, text
import streamlit.components.v1 as components
import secrets

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

# Conexão blindada com o Supabase
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

# --- SISTEMA DE AUTENTICAÇÃO COM LINK ÚNICO E SENHA ---
def garantir_chave_acesso(user_id):
    nova_chave = secrets.token_urlsafe(20)
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE usuarios 
                SET chave_acesso = :k 
                WHERE id = :uid AND chave_acesso IS NULL;
            """), {"k": nova_chave, "uid": user_id})
        return nova_chave
    except Exception:
        return None

def buscar_usuario_por_chave(chave_acesso):
    if not chave_acesso:
        return None
    try:
        with engine.connect() as conn:
            query = text("""
                SELECT id, email, nome, ativo, COALESCE(primeiro_acesso, FALSE) AS primeiro_acesso, chave_acesso
                FROM usuarios 
                WHERE chave_acesso = :chave
                LIMIT 1;
            """)
            result = conn.execute(query, {"chave": chave_acesso.strip()}).fetchone()
            if result:
                return {
                    "id": result[0],
                    "email": result[1],
                    "nome": result[2],
                    "ativo": bool(result[3]),
                    "primeiro_acesso": bool(result[4]),
                    "chave_acesso": result[5]
                }
            return None
    except Exception as e:
        st.error(f"Erro ao validar chave de acesso: {str(e)}")
        return None

def autenticar_usuario_senha(email_digitado, senha_digitada):
    try:
        with engine.connect() as conn:
            query = text("""
                SELECT id, email, nome, ativo, COALESCE(primeiro_acesso, FALSE) AS primeiro_acesso, chave_acesso
                FROM usuarios 
                WHERE LOWER(email) = LOWER(:email) 
                  AND (
                      senha_hash = crypt(:senha, senha_hash)
                      OR senha_hash = :senha
                  )
                LIMIT 1;
            """)
            result = conn.execute(query, {
                "email": email_digitado.strip(),
                "senha": senha_digitada
            }).fetchone()
            
            if result:
                user_dict = {
                    "id": result[0],
                    "email": result[1],
                    "nome": result[2],
                    "ativo": bool(result[3]),
                    "primeiro_acesso": bool(result[4]),
                    "chave_acesso": result[5]
                }
                if not user_dict["chave_acesso"]:
                    user_dict["chave_acesso"] = garantir_chave_acesso(user_dict["id"])
                return user_dict
            return None
    except Exception as e:
        st.error(f"Erro ao verificar credenciais: {str(e)}")
        return None

def atualizar_senha_primeiro_acesso(user_id, nova_senha):
    try:
        with engine.begin() as conn:
            up_query = text("""
                UPDATE usuarios 
                SET senha_hash = crypt(:nova_senha, gen_salt('bf')),
                    primeiro_acesso = FALSE
                WHERE id = :uid;
            """)
            conn.execute(up_query, {"uid": user_id, "nova_senha": nova_senha})
            return True, "Senha cadastrada com sucesso!"
    except Exception as e:
        return False, f"Erro ao definir nova senha: {str(e)}"

def atualizar_senha_usuario(user_id, senha_atual, nova_senha):
    try:
        with engine.begin() as conn:
            check_query = text("""
                SELECT id FROM usuarios 
                WHERE id = :uid 
                  AND (
                      senha_hash = crypt(:senha_atual, senha_hash)
                      OR senha_hash = :senha_atual
                  );
            """)
            valido = conn.execute(check_query, {"uid": user_id, "senha_atual": senha_atual}).fetchone()
            if not valido:
                return False, "A senha atual informada está incorreta."

            up_query = text("""
                UPDATE usuarios 
                SET senha_hash = crypt(:nova_senha, gen_salt('bf')),
                    primeiro_acesso = FALSE
                WHERE id = :uid;
            """)
            conn.execute(up_query, {"uid": user_id, "nova_senha": nova_senha})
            return True, "Senha alterada com sucesso!"
    except Exception as e:
        return False, f"Erro ao atualizar senha: {str(e)}"

def verificar_login():
    if "usuario_logado" not in st.session_state:
        st.session_state["usuario_logado"] = None

    # 1. VERIFICAÇÃO AUTOMÁTICA VIA LINK ÚNICO (?acesso=chave)
    chave_url = st.query_params.get("acesso")
    if chave_url and st.session_state["usuario_logado"] is None:
        user_chave = buscar_usuario_por_chave(chave_url)
        if user_chave:
            if user_chave["ativo"]:
                st.session_state["usuario_logado"] = user_chave
                return True
            else:
                st.error("⛔ Sua assinatura está inativa. Regularize na plataforma de compra.")
                st.stop()
        else:
            st.warning("⚠️ Link de acesso inválido ou expirado. Faça login manualmente.")
            st.query_params.clear()

    if st.session_state["usuario_logado"] is not None:
        return True

    # 2. TELA DE LOGIN CONVENCIONAL
    col_vazia1, col_centro, col_vazia2 = st.columns([1, 2.5, 1])
    with col_centro:
        st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
        st.markdown("### 🔒 Acesso ao Sistema")
        st.caption("Introduza seu e-mail e senha cadastrados para entrar.")

        with st.form("form_login"):
            email_input = st.text_input("E-mail", placeholder="seu_email@exemplo.com").strip().lower()
            senha_input = st.text_input("Senha", type="password", placeholder="••••••••")
            btn_entrar = st.form_submit_button("🔓 Entrar", use_container_width=True, type="primary")

            if btn_entrar:
                if not email_input or not senha_input:
                    st.error("Por favor, preencha o e-mail e a senha.")
                else:
                    dados_user = autenticar_usuario_senha(email_input, senha_input)
                    if dados_user:
                        if not dados_user["ativo"]:
                            st.error("⛔ A sua assinatura está inativa. Regularize o acesso para continuar.")
                        else:
                            st.session_state["usuario_logado"] = dados_user
                            # Anexa a chave única na URL para salvar nos favoritos/tela inicial
                            if dados_user.get("chave_acesso"):
                                st.query_params["acesso"] = dados_user["chave_acesso"]
                            st.rerun()
                    else:
                        st.error("E-mail ou senha incorretos. Verifique suas credenciais.")

    return False

if not verificar_login():
    st.stop()

# Usuário logado
usuario_atual = st.session_state["usuario_logado"]
USUARIO_ID = usuario_atual["id"]
NOME_EXIBICAO = usuario_atual["nome"] if usuario_atual["nome"] else usuario_atual["email"]
CHAVE_ACESSO = usuario_atual.get("chave_acesso", "")

# Garante que o parâmetro de acesso continue na URL durante a navegação
if CHAVE_ACESSO and st.query_params.get("acesso") != CHAVE_ACESSO:
    st.query_params["acesso"] = CHAVE_ACESSO

# --- BLOQUEIO E TELA OBRIGATÓRIA DE PRIMEIRO ACESSO ---
if usuario_atual.get("primeiro_acesso", False):
    col_v1, col_centro, col_v2 = st.columns([1, 2.5, 1])
    with col_centro:
        st.markdown("<div style='height: 30px;'></div>", unsafe_allow_html=True)
        st.markdown("### 🛡️ Defina sua Senha Pessoal")
        st.info("👋 Olá! Este é o seu primeiro acesso. Defina uma senha segura para sua conta.")

        with st.form("form_primeiro_acesso"):
            nova_senha_pa = st.text_input("Nova Senha:", type="password", placeholder="Mínimo 6 caracteres")
            conf_senha_pa = st.text_input("Confirme a Nova Senha:", type="password", placeholder="Repita a nova senha")
            btn_salvar_pa = st.form_submit_button("💾 Salvar Senha e Liberar Acesso", type="primary", use_container_width=True)

            if btn_salvar_pa:
                if not nova_senha_pa or not conf_senha_pa:
                    st.error("Preencha todos os campos.")
                elif len(nova_senha_pa) < 6:
                    st.error("A nova senha deve ter no mínimo 6 caracteres.")
                elif nova_senha_pa != conf_senha_pa:
                    st.error("As senhas digitadas não coincidem.")
                else:
                    sucesso, msg = atualizar_senha_primeiro_acesso(USUARIO_ID, nova_senha_pa)
                    if sucesso:
                        usuario_atual["primeiro_acesso"] = False
                        st.session_state["usuario_logado"] = usuario_atual
                        st.session_state["msg_sucesso"] = "Senha definida com sucesso! Bem-vindo ao painel."
                        st.rerun()
                    else:
                        st.error(msg)
    st.stop()

# Modal para Exibir Link Único do Motorista
@st.dialog("🔗 Seu Link de Acesso Direto")
def modal_link_direto(chave):
    st.write("Guarde este link nos favoritos ou adicione à tela de início do seu celular. Com ele, você entra direto sem digitar senha:")
    link_direto = f"https://seu-app.streamlit.app/?acesso={chave}"
    st.code(link_direto, language="text")
    st.caption("📲 **No iPhone ou Android:** Abra este link e clique em 'Adicionar à tela de início' para criar um ícone que abre seu app direto!")

# Modal para Alteração de Senha
@st.dialog("🔑 Alterar Palavra-passe")
def modal_alterar_senha(user_id):
    st.write("Crie uma nova senha de acesso segura para sua conta.")
    with st.form("form_mudar_senha"):
        s_atual = st.text_input("Senha Atual:", type="password", placeholder="Sua senha atual")
        s_nova = st.text_input("Nova Senha:", type="password", placeholder="No mínimo 6 caracteres")
        s_conf = st.text_input("Confirme a Nova Senha:", type="password", placeholder="Repita a nova senha")
        
        btn_salvar_senha = st.form_submit_button("💾 Atualizar Senha", type="primary", use_container_width=True)

        if btn_salvar_senha:
            if not s_atual or not s_nova or not s_conf:
                st.error("Preencha todos os campos.")
            elif len(s_nova) < 6:
                st.error("A nova senha deve ter pelo menos 6 caracteres.")
            elif s_nova != s_conf:
                st.error("A confirmação não coincide com a nova senha.")
            else:
                ok, msg = atualizar_senha_usuario(user_id, s_atual, s_nova)
                if ok:
                    st.session_state["msg_sucesso"] = "Senha atualizada com sucesso!"
                    st.rerun()
                else:
                    st.error(msg)

# --- BARRA SUPERIOR COM IDENTIFICAÇÃO E AÇÕES ---
c_titulo, c_link, c_senha, c_sair = st.columns([3.0, 1.4, 1.2, 1.0])
with c_titulo:
    st.title("🚗 Gestão de Turnos & Finanças")
    st.caption(f"👤 Conectado como: **{NOME_EXIBICAO}**")
with c_link:
    st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
    if st.button("🔗 Meu Link", use_container_width=True, help="Ver link de acesso direto"):
        modal_link_direto(CHAVE_ACESSO)
with c_senha:
    st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
    if st.button("🔑 Senha", use_container_width=True, help="Alterar senha"):
        modal_alterar_senha(USUARIO_ID)
with c_sair:
    st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
    if st.button("🚪 Sair", use_container_width=True):
        st.query_params.clear()
        st.session_state["usuario_logado"] = None
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

# Operações de Banco de Dados com Filtro por Usuário
@st.cache_data(ttl=600)
def carregar_dados(user_id):
    with engine.connect() as conn:
        df = pd.read_sql_query(
            text("SELECT * FROM lancamentos WHERE usuario_id = :uid ORDER BY data DESC, id DESC"), 
            conn, 
            params={"uid": user_id}
        )
    
    if not df.empty:
        df["data"] = pd.to_datetime(df["data"])
        df["valor"] = df["valor"].astype(float)
        df["categoria"] = df["categoria"].replace({
            "Uber": "Uber sem pedágios",
            "99": "99 com pedágios"
        })
    else:
        df = pd.DataFrame(columns=["id", "data", "tipo", "categoria", "descricao", "valor", "usuario_id"])
        df["data"] = pd.to_datetime(df["data"])
        df["valor"] = df["valor"].astype(float)
    return df

@st.cache_data(ttl=600)
def carregar_turnos_km(user_id):
    with engine.connect() as conn:
        df_km = pd.read_sql_query(
            text("SELECT * FROM turnos_km WHERE usuario_id = :uid ORDER BY data DESC, id ASC"), 
            conn, 
            params={"uid": user_id}
        )
    
    if not df_km.empty:
        df_km["data"] = pd.to_datetime(df_km["data"])
        df_km["km_inicial"] = pd.to_numeric(df_km["km_inicial"], errors="coerce")
        df_km["km_final"] = pd.to_numeric(df_km["km_final"], errors="coerce")
        df_km["km_rodado"] = pd.to_numeric(df_km["km_rodado"], errors="coerce")
    else:
        df_km = pd.DataFrame(columns=["id", "data", "km_inicial", "km_final", "km_rodado", "usuario_id"])
        df_km["data"] = pd.to_datetime(df_km["data"])
    return df_km

def abrir_novo_turno(data_reg, km_ini, user_id):
    with engine.begin() as conn:
        conn.execute(text('''
            INSERT INTO turnos_km (data, km_inicial, usuario_id)
            VALUES (:data, :km_inicial, :uid);
        '''), {"data": data_reg, "km_inicial": km_ini, "uid": user_id})
    carregar_turnos_km.clear()

def fechar_turno(turno_id, km_fim, km_rodado, user_id):
    with engine.begin() as conn:
        conn.execute(text('''
            UPDATE turnos_km
            SET km_final = :km_fim, km_rodado = :km_rodado
            WHERE id = :id AND usuario_id = :uid;
        '''), {"km_fim": km_fim, "km_rodado": km_rodado, "id": turno_id, "uid": user_id})
    carregar_turnos_km.clear()

def editar_turno_banco(turno_id, km_ini, km_fim, user_id):
    km_rod = (km_fim - km_ini) if (km_fim is not None and km_fim >= km_ini) else None
    with engine.begin() as conn:
        conn.execute(text('''
            UPDATE turnos_km
            SET km_inicial = :km_ini, km_final = :km_fim, km_rodado = :km_rod
            WHERE id = :id AND usuario_id = :uid;
        '''), {"km_ini": km_ini, "km_fim": km_fim, "km_rod": km_rod, "id": turno_id, "uid": user_id})
    carregar_turnos_km.clear()

def deletar_turno_banco(turno_id, user_id):
    with engine.begin() as conn:
        conn.execute(text('DELETE FROM turnos_km WHERE id = :id AND usuario_id = :uid'), {"id": turno_id, "uid": user_id})
    carregar_turnos_km.clear()

def inserir_registro_avulso(data_reg, tipo, categoria, descricao, valor, user_id):
    with engine.begin() as conn:
        conn.execute(text('''
            INSERT INTO lancamentos (data, tipo, categoria, descricao, valor, usuario_id)
            VALUES (:data, :tipo, :categoria, :descricao, :valor, :uid)
        '''), {"data": data_reg, "tipo": tipo, "categoria": categoria, "descricao": descricao, "valor": valor, "uid": user_id})
    carregar_dados.clear()

def salvar_fechamento_em_lote(data_reg, lista_lancamentos, user_id):
    with engine.begin() as conn:
        for item in lista_lancamentos:
            conn.execute(text('''
                INSERT INTO lancamentos (data, tipo, categoria, descricao, valor, usuario_id)
                VALUES (:data, :tipo, :categoria, :descricao, :valor, :uid)
            '''), {
                "data": data_reg,
                "tipo": item["tipo"],
                "categoria": item["categoria"],
                "descricao": item["descricao"],
                "valor": item["valor"],
                "uid": user_id
            })
    carregar_dados.clear()

def atualizar_registro(id_reg, data_reg, tipo, categoria, descricao, valor, user_id):
    with engine.begin() as conn:
        conn.execute(text('''
            UPDATE lancamentos
            SET data = :data, tipo = :tipo, categoria = :categoria, descricao = :descricao, valor = :valor
            WHERE id = :id AND usuario_id = :uid
        '''), {"data": data_reg, "tipo": tipo, "categoria": categoria, "descricao": descricao, "valor": valor, "id": id_reg, "uid": user_id})
    carregar_dados.clear()

def deletar_registro(id_reg, user_id):
    with engine.begin() as conn:
        conn.execute(text('DELETE FROM lancamentos WHERE id = :id AND usuario_id = :uid'), {"id": id_reg, "uid": user_id})
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

# Carregamento filtrado pelo usuário logado
df_completo = carregar_dados(USUARIO_ID)
df_turnos_km = carregar_turnos_km(USUARIO_ID)

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
                editar_turno_banco(turno_id, p_ini, p_fim, USUARIO_ID)
                st.session_state["msg_sucesso"] = "Turno atualizado com sucesso!"
                st.rerun()
    with col2:
        if st.button("✖️ Cancelar", use_container_width=True):
            st.rerun()

# Modal Dinâmico de Edição do Dia
@st.dialog("✏️ Editar Lançamento do Dia")
def modal_editar_lancamento_dia(data_ref, lancamentos_dia_df):
    if lancamentos_dia_df.empty:
        st.info("Nenhum lançamento registrado nesta data.")
        return

    mapa_itens = {}
    lista_rotulos = []
    for _, r in lancamentos_dia_df.iterrows():
        rid = int(r["id"])
        rotulo = f"#{rid} - {r['categoria']} ({formata_real(r['valor'])})"
        mapa_itens[rotulo] = {
            "id": rid,
            "tipo": r["tipo"],
            "categoria": r["categoria"],
            "valor": float(r["valor"]),
            "descricao": r["descricao"] if r["descricao"] else ""
        }
        lista_rotulos.append(rotulo)

    rotulo_selecionado = st.selectbox(
        "Selecione o registro para editar (apenas com registro ativo):", 
        lista_rotulos, 
        key="sel_edicao_parcial_dia"
    )
    
    item_ativo = mapa_itens[rotulo_selecionado]
    item_id = item_ativo["id"]
    badge = "🟢" if item_ativo["tipo"] == "Receita" else "🔴"
    st.markdown(f"**Tipo:** {badge} **{item_ativo['tipo']}** | **Categoria:** `{item_ativo['categoria']}`")

    with st.form(f"form_ed_dinamico_{item_id}"):
        novo_val_str = st.text_input(
            "Valor (R$):", 
            value=f"{item_ativo['valor']:.2f}".replace(".", ","),
            key=f"val_ed_{item_id}"
        )
        nova_desc = st.text_input(
            "Observação:", 
            value=item_ativo["descricao"],
            key=f"desc_ed_{item_id}"
        )

        col_b1, col_b2 = st.columns(2)
        with col_b1:
            btn_salvar = st.form_submit_button("💾 Salvar Alterações", type="primary", use_container_width=True)
        with col_b2:
            btn_excluir = st.form_submit_button("🗑️ Excluir Registro", use_container_width=True)

        if btn_salvar:
            v_num = converter_valor(novo_val_str)
            if v_num <= 0:
                st.error("Informe um valor maior que zero.")
            else:
                atualizar_registro(item_id, data_ref, item_ativo["tipo"], item_ativo["categoria"], nova_desc.strip(), v_num, USUARIO_ID)
                st.session_state["msg_sucesso"] = f"Lançamento #{item_id} atualizado com sucesso!"
                st.rerun()

        if btn_excluir:
            deletar_registro(item_id, USUARIO_ID)
            st.session_state["msg_sucesso"] = f"Lançamento #{item_id} excluído com sucesso!"
            st.rerun()

# Modal Padrão de Edição (Aba Histórico)
@st.dialog("✏️ Editar Lançamento")
def modal_editar_registro(item_id, item_data, item_tipo, item_cat, item_desc, item_val):
    badge = "🟢" if item_tipo == "Receita" else "🔴"
    st.markdown(f"**Tipo:** {badge} **{item_tipo}**")
    
    with st.form(f"form_ed_{item_id}"):
        novo_val_str = st.text_input(
            "Valor (R$):", 
            value=f"{float(item_val):.2f}".replace(".", ",")
        )
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
                atualizar_registro(item_id, item_data, item_tipo, cat_final, nova_desc, v_num, USUARIO_ID)
                st.session_state["msg_sucesso"] = f"Lançamento #{item_id} atualizado!"
                st.rerun()

@st.dialog("🗑️ Confirmar Exclusão")
def modal_excluir_registro(item_id, item_cat, item_val_formatado):
    st.write(f"Deseja excluir o lançamento **#{item_id}**?")
    st.markdown(f"**{item_cat}** — **{item_val_formatado}**")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✔️ Sim, excluir", type="primary", use_container_width=True):
            deletar_registro(item_id, USUARIO_ID)
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
    st.caption(f"🗓️ A gerir o dia: **{data_atual.strftime('%d/%m/%Y')}** ({DIAS_SEMANA_PT[data_atual.weekday()]})")

    # Filtra turnos e lançamentos do dia
    turnos_do_dia = df_turnos_km[df_turnos_km["data"].dt.date == data_atual].sort_values("id") if not df_turnos_km.empty else pd.DataFrame()
    turno_aberto = turnos_do_dia[turnos_do_dia["km_final"].isnull()] if not turnos_do_dia.empty else pd.DataFrame()
    tem_turno_aberto = not turno_aberto.empty
    total_km_dia = int(round(turnos_do_dia["km_rodado"].dropna().sum())) if not turnos_do_dia.empty else 0

    lancamentos_hoje = df_completo[df_completo["data"].dt.date == data_atual] if not df_completo.empty else pd.DataFrame()

    # --- SEÇÃO 1: TURNOS DE QUILOMETRAGEM ---
    st.markdown("---")
    st.markdown("#### 🚗 1. Turnos de Trabalho (Quilometragem)")
    st.caption("Inicie um turno ao começar a trabalhar e feche ao pausar para atividades particulares.")

    if not turnos_do_dia.empty:
        st.markdown(f"**Turnos de trabalho no dia:** (Total acumulado: **{formata_km(total_km_dia)}**)")
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
                    st.markdown(f"⏳ **Turno {idx_t} (EM CURSO):** Aberto em **{k_ini:,} km**".replace(",", "."))
            with col_t_edit:
                if st.button("✏️", key=f"btn_ed_turno_{t_id}", use_container_width=True):
                    modal_editar_turno(t_id, k_ini, k_fim)
            with col_t_del:
                if st.button("🗑️", key=f"btn_del_turno_{t_id}", use_container_width=True):
                    deletar_turno_banco(t_id, USUARIO_ID)
                    st.session_state["msg_sucesso"] = f"Turno #{t_id} removido."
                    st.rerun()
            idx_t += 1

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
                    st.error("Indique um KM final válido.")
                elif val_kf < km_ini_ativo:
                    st.error(f"O KM final não pode ser menor que o inicial ({km_ini_ativo:,} km).".replace(",", "."))
                else:
                    km_rodado_calc = val_kf - km_ini_ativo
                    fechar_turno(id_aberto, val_kf, km_rodado_calc, USUARIO_ID)
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
                    st.error("Indique um KM inicial inteiro e válido.")
                else:
                    abrir_novo_turno(data_atual, val_ki, USUARIO_ID)
                    st.session_state["msg_sucesso"] = f"Turno iniciado em {val_ki:,} km!".replace(",", ".")
                    st.rerun()

    # --- SEÇÃO 2: LANÇAMENTO RÁPIDO PARCIAL ---
    st.markdown("---")
    st.markdown("#### ⚡ 2. Lançamento Rápido no Dia (Despesas ou Ganhos)")
    st.caption("Abasteceu, lavou o veículo ou recebeu uma corrida avulsa? Salve aqui imediatamente.")

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
            placeholder_espec = "Ex: Corrida particular avulsa, Gorjeta..." if eh_rec else "Ex: Estacionamento, Lanche, Troca de óleo..."
            cat_espec = st.text_input("Especifique a categoria *", placeholder=placeholder_espec)
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
                st.error("Indique um valor superior a zero.")
            elif cat_avulsa_sel == "Outro" and not cat_final_avulsa:
                st.error("Indique o nome da categoria 'Outro'.")
            else:
                tipo_bd = "Receita" if eh_rec else "Despesa"
                inserir_registro_avulso(data_atual, tipo_bd, cat_final_avulsa, obs_avulsa.strip(), v_calc, USUARIO_ID)
                st.session_state["msg_sucesso"] = f"{tipo_bd} de {formata_real(v_calc)} salva com sucesso!"
                st.rerun()

    # --- SEÇÃO 3: FECHAMENTO GERAL DO DIA ---
    st.markdown("---")
    st.markdown("#### 🏁 3. Fechamento Geral do Dia (Checklist Final)")
    st.caption("Consolide o encerramento do dia: valide os KMs totais, itens já salvos e lance os pendentes.")

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

    # Mapeamento dos itens já lançados hoje
    categorias_lancadas_hoje = {}
    if not lancamentos_hoje.empty:
        for _, row in lancamentos_hoje.iterrows():
            categorias_lancadas_hoje[row["categoria"]] = {
                "id": int(row["id"]),
                "tipo": row["tipo"],
                "valor": float(row["valor"]),
                "descricao": row["descricao"] if row["descricao"] else ""
            }

    with st.form("form_fechamento_geral_dia"):
        st.markdown("##### 🟢 Ganhos (Receitas do Dia):")
        
        campos_pendentes_rec = {}
        for cat in OPCOES_RECEITA_FIXAS:
            if cat in categorias_lancadas_hoje:
                dados_cat = categorias_lancadas_hoje[cat]
                st.text_input(
                    f"✔️ {cat} (Já Registrado - Bloqueado):",
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

        col_or1, col_or2 = st.columns([1.2, 2])
        with col_or1:
            val_outra_rec = st.text_input("Outra Receita (R$):", placeholder="0,00", key="fech_outra_rec_val")
        with col_or2:
            obs_outra_rec = st.text_input("Especifique a outra receita:", placeholder="Ex: Gorjeta no app, Entrega particular...", key="fech_outra_rec_obs")

        st.markdown("---")
        st.markdown("##### 🔴 Despesas do Dia:")
        
        campos_pendentes_desp = {}
        for cat in OPCOES_DESPESA_FIXAS:
            if cat in categorias_lancadas_hoje:
                dados_cat = categorias_lancadas_hoje[cat]
                st.text_input(
                    f"✔️ {cat} (Já Registrado - Bloqueado):",
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

        col_od1, col_od2 = st.columns([1.2, 2])
        with col_od1:
            val_outro_fechamento = st.text_input("Outro Custo (R$):", placeholder="0,00", key="fech_outro_val")
        with col_od2:
            obs_outro_fechamento = st.text_input("Especifique o outro custo:", placeholder="Ex: Troca de lâmpada, café...", key="fech_outro_obs")

        btn_concluir_dia = st.form_submit_button("🏁 Gravar Fechamento Final do Dia", type="primary", use_container_width=True)

        if btn_concluir_dia:
            novos_itens = []

            for cat, campo_val in campos_pendentes_rec.items():
                v = converter_valor(campo_val)
                if v > 0:
                    novos_itens.append({"tipo": "Receita", "categoria": cat, "descricao": "", "valor": v})

            v_outra_rec_num = converter_valor(val_outra_rec)
            if v_outra_rec_num > 0:
                novos_itens.append({"tipo": "Receita", "categoria": "Outro", "descricao": obs_outra_rec.strip(), "valor": v_outra_rec_num})

            for cat, campo_val in campos_pendentes_desp.items():
                v = converter_valor(campo_val)
                if v > 0:
                    novos_itens.append({"tipo": "Despesa", "categoria": cat, "descricao": "", "valor": v})

            v_outro_num = converter_valor(val_outro_fechamento)
            if v_outro_num > 0:
                novos_itens.append({"tipo": "Despesa", "categoria": "Outro", "descricao": obs_outro_fechamento.strip(), "valor": v_outro_num})

            if not novos_itens and not categorias_lancadas_hoje and total_km_dia == 0:
                st.warning("Preencha pelo menos uma categoria pendente para concluir o fecho.")
            else:
                if novos_itens:
                    salvar_fechamento_em_lote(data_atual, novos_itens, USUARIO_ID)
                st.session_state["msg_sucesso"] = f"Fechamento do dia {data_atual.strftime('%d/%m/%Y')} concluído com sucesso!"
                st.rerun()

    # Painel dos itens registrados hoje com botão de edição dinâmico
    if not lancamentos_hoje.empty:
        col_cab_hoje, col_btn_ed_hoje = st.columns([4, 1.5])
        with col_cab_hoje:
            st.markdown(f"**Itens já lançados hoje ({len(lancamentos_hoje)}):**")
        with col_btn_ed_hoje:
            if st.button("✏️ Editar Lançamento", key="btn_abrir_modal_dia", use_container_width=True):
                modal_editar_lancamento_dia(data_atual, lancamentos_hoje)

        for _, row in lancamentos_hoje.iterrows():
            t_icon = "🟢" if row["tipo"] == "Receita" else "🔴"
            obs_txt = f" - *{row['descricao']}*" if row["descricao"] else ""
            st.markdown(f"{t_icon} **{row['categoria']}**: **{formata_real(row['valor'])}**{obs_txt}")

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

        st.caption(f"A exibir {min(len(df_lista), 40)} de {len(df_lista)} lançamentos")

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
    df_f = pd.DataFrame(columns=["id", "data", "tipo", "categoria", "descricao", "valor", "usuario_id"])

if not df_turnos_km.empty:
    df_km_f = df_turnos_km[(df_turnos_km["data"].dt.date >= d_inicio) & (df_turnos_km["data"].dt.date <= d_fim)].copy()
else:
    df_km_f = pd.DataFrame(columns=["id", "data", "km_inicial", "km_final", "km_rodado", "usuario_id"])

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

# 2. CARDS DE EFICIÊNCIA DE QUILOMETRAGEM
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

# --- GRÁFICOS: DISTRIBUIÇÃO E EVOLUÇÃO ---
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
