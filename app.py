import streamlit as st
import pandas as pd
from datetime import date, timedelta
import plotly.express as px
from sqlalchemy import create_engine, text
import streamlit.components.v1 as components
import hmac

st.set_page_config(
    page_title="Controle Motorista App", 
    page_icon="🚗", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Estilização visual moderna e compacta para celular
st.markdown("""
<style>
    div[data-testid="stMetricValue"] > div {
        font-size: 1.4rem !important;
        font-weight: 700 !important;
    }
    .stButton button {
        border-radius: 8px;
    }
    .card-registro {
        padding: 10px 14px;
        border-radius: 8px;
        background-color: rgba(128, 128, 128, 0.07);
        margin-bottom: 8px;
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

    # Tela de Acesso
    col_vazia1, col_centro, col_vazia2 = st.columns([1, 2.5, 1])
    with col_centro:
        st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
        st.markdown("### 🔒 Acesso Restrito")
        st.caption("Digite suas credenciais para acessar o painel financeiro.")

        with st.form("form_login"):
            usuario_input = st.text_input("Usuário", placeholder="Ex: admin").strip()
            senha_input = st.text_input("Senha", type="password", placeholder="••••••••")
            btn_entrar = st.form_submit_button("🔓 Entrar", use_container_width=True, type="primary")

            if btn_entrar:
                # Comparações seguras contra timing attacks
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

# --- BARRA SUPERIOR DE CABEÇALHO COM LOGOUT ---
c_titulo, c_sair = st.columns([4, 1.2])
with c_titulo:
    st.title("🚗 Gestão Financeira")
with c_sair:
    st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
    if st.button("🚪 Sair", use_container_width=True):
        st.session_state["autenticado"] = False
        st.rerun()

# Opções fixas
OPCOES_RECEITA_FIXAS = ["Uber", "99", "Pedágio Uber", "Particular"]
OPCOES_DESPESA_FIXAS = ["Combustível", "Lavagem", "SemParar do dia"]

OPCOES_RECEITA_FORM = OPCOES_RECEITA_FIXAS + ["Outro"]
OPCOES_DESPESA_FORM = OPCOES_DESPESA_FIXAS + ["Outro"]

# Função auxiliar para formatação em Real brasileiro (R$ 1.250,50)
def formata_real(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# Converte qualquer entrada numérica/texto com vírgula ou ponto em float válido
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

# Conexão blindada com o Supabase via Secrets do Streamlit Cloud
raw_url = st.secrets["database"]["url"]

if raw_url.startswith("postgresql://"):
    raw_url = raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
elif raw_url.startswith("postgres://"):
    raw_url = raw_url.replace("postgres://", "postgresql+psycopg://", 1)

if "sslmode" not in raw_url:
    raw_url += "?sslmode=require" if "?" not in raw_url else "&sslmode=require"

engine = create_engine(
    raw_url,
    pool_pre_ping=True,
    pool_recycle=300
)

def init_db():
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
    except Exception as e:
        st.error(f"Erro de conexão com o banco de dados: {str(e)}")
        st.stop()

def inserir_registro(data_reg, tipo, categoria, descricao, valor):
    with engine.begin() as conn:
        conn.execute(
            text('''
                INSERT INTO lancamentos (data, tipo, categoria, descricao, valor)
                VALUES (:data, :tipo, :categoria, :descricao, :valor)
            '''),
            {"data": data_reg, "tipo": tipo, "categoria": categoria, "descricao": descricao, "valor": valor}
        )

def atualizar_registro(id_reg, data_reg, tipo, categoria, descricao, valor):
    with engine.begin() as conn:
        conn.execute(
            text('''
                UPDATE lancamentos
                SET data = :data, tipo = :tipo, categoria = :categoria, descricao = :descricao, valor = :valor
                WHERE id = :id
            '''),
            {"data": data_reg, "tipo": tipo, "categoria": categoria, "descricao": descricao, "valor": valor, "id": id_reg}
        )

def deletar_registro(id_reg):
    with engine.begin() as conn:
        conn.execute(text('DELETE FROM lancamentos WHERE id = :id'), {"id": id_reg})

def carregar_dados():
    with engine.connect() as conn:
        df = pd.read_sql_query(text("SELECT * FROM lancamentos ORDER BY data DESC, id DESC"), conn)
    if not df.empty:
        df["data"] = pd.to_datetime(df["data"])
        df["valor"] = df["valor"].astype(float)
    return df

init_db()

df_completo = carregar_dados()

# Notificação temporária de sucesso
if "msg_sucesso" in st.session_state:
    st.success(st.session_state.pop("msg_sucesso"))

# Estado da data
if "data_novo_lancamento" not in st.session_state:
    st.session_state["data_novo_lancamento"] = date.today()

if "novo_date_key_ver" not in st.session_state:
    st.session_state["novo_date_key_ver"] = 0

# Modal de Edição
@st.dialog("✏️ Editar Lançamento")
def modal_editar_registro(item_id, item_data, item_tipo, item_cat, item_desc, item_val):
    badge = "🟢" if item_tipo == "Receita" else "🔴"
    st.markdown(f"**Tipo:** {badge} **{item_tipo}**")
    
    chave_data = f"data_ed_{item_id}"
    chave_ver = f"ver_ed_{item_id}"
    
    if chave_data not in st.session_state:
        st.session_state[chave_data] = item_data
    if chave_ver not in st.session_state:
        st.session_state[chave_ver] = 0

    st.markdown("**Data do Registro:**")
    col_eh, col_eo, col_ed = st.columns([1, 1, 2])
    
    with col_eh:
        if st.button("Hoje", key=f"btn_h_{item_id}", use_container_width=True):
            st.session_state[chave_data] = date.today()
            st.session_state[chave_ver] += 1
            st.rerun()
    with col_eo:
        if st.button("Ontem", key=f"btn_o_{item_id}", use_container_width=True):
            st.session_state[chave_data] = date.today() - timedelta(days=1)
            st.session_state[chave_ver] += 1
            st.rerun()
    with col_ed:
        nova_data = st.date_input(
            "Selecionar data",
            value=st.session_state[chave_data],
            key=f"ed_dt_{item_id}_{st.session_state[chave_ver]}",
            label_visibility="collapsed"
        )
        st.session_state[chave_data] = nova_data

    with st.form(f"form_dialog_edicao_{item_id}"):
        novo_val_str = st.text_input("Valor (R$):", value=f"{float(item_val):.2f}".replace(".", ","))

        opcoes_lista = OPCOES_RECEITA_FORM if item_tipo == "Receita" else OPCOES_DESPESA_FORM
        
        if item_cat in opcoes_lista and item_cat != "Outro":
            idx = opcoes_lista.index(item_cat)
            custom_txt = ""
        else:
            idx = opcoes_lista.index("Outro")
            custom_txt = item_cat

        cat_sel = st.selectbox("Categoria:", opcoes_lista, index=idx)
        if cat_sel == "Outro":
            cat_final = st.text_input("Especifique a categoria *", value=custom_txt).strip()
        else:
            cat_final = cat_sel

        nova_desc = st.text_input("Observação:", value=item_desc if item_desc else "").strip()

        btn_salvar_dialog = st.form_submit_button("💾 Salvar Alterações", type="primary", use_container_width=True)

        if btn_salvar_dialog:
            v_num = converter_valor(novo_val_str)
            if v_num <= 0:
                st.error("O valor informado deve ser superior a zero.")
            elif cat_sel == "Outro" and not cat_final:
                st.error("Indique o nome da categoria 'Outro'.")
            else:
                atualizar_registro(item_id, st.session_state[chave_data], item_tipo, cat_final, nova_desc, v_num)
                st.session_state.pop(chave_data, None)
                st.session_state.pop(chave_ver, None)
                st.session_state["msg_sucesso"] = f"Lançamento ID #{item_id} atualizado com sucesso!"
                st.rerun()

    if st.button("✖️ Cancelar e Fechar", use_container_width=True):
        st.session_state.pop(chave_data, None)
        st.session_state.pop(chave_ver, None)
        st.rerun()

@st.dialog("🗑️ Confirmar Exclusão")
def modal_excluir_registro(item_id, item_cat, item_val_formatado):
    st.write(f"Deseja excluir permanentemente o lançamento **ID #{item_id}**?")
    st.markdown(f"**{item_cat}** — **{item_val_formatado}**")
    st.caption("Esta operação não pode ser revertida.")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✔️ Sim, excluir", type="primary", use_container_width=True):
            deletar_registro(item_id)
            st.session_state["msg_sucesso"] = f"Lançamento ID #{item_id} excluído com sucesso!"
            st.rerun()
    with col2:
        if st.button("✖️ Cancelar", use_container_width=True):
            st.rerun()

# Abas Nativas
tab_novo, tab_gerenciar = st.tabs(["➕ Novo Lançamento", "⚙️ Gerenciar Registros"])

# --- ABA 1: NOVO LANÇAMENTO ---
with tab_novo:
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        tipo_escolhido = st.radio("Tipo", ["Receita (Ganhos)", "Despesa (Custos)"], horizontal=True, key="novo_tipo_radio")
    
    eh_receita = tipo_escolhido == "Receita (Ganhos)"
    opcoes_cat = OPCOES_RECEITA_FORM if eh_receita else OPCOES_DESPESA_FORM

    with col_t2:
        cat_selecionada = st.selectbox("Categoria / Atividade", opcoes_cat, key="novo_cat_box")

    st.markdown("**Data do Lançamento:**")
    col_h, col_o, col_d = st.columns([1, 1, 2])
    
    with col_h:
        if st.button("📅 Hoje", use_container_width=True):
            st.session_state["data_novo_lancamento"] = date.today()
            st.session_state["novo_date_key_ver"] += 1
            st.rerun()
            
    with col_o:
        if st.button("📅 Ontem", use_container_width=True):
            st.session_state["data_novo_lancamento"] = date.today() - timedelta(days=1)
            st.session_state["novo_date_key_ver"] += 1
            st.rerun()
            
    with col_d:
        data_escolhida = st.date_input(
            "Selecionar data",
            value=st.session_state["data_novo_lancamento"],
            key=f"input_date_novo_{st.session_state['novo_date_key_ver']}",
            label_visibility="collapsed"
        )
        st.session_state["data_novo_lancamento"] = data_escolhida

    st.caption(f"🗓️ Data definida: **{st.session_state['data_novo_lancamento'].strftime('%d/%m/%Y')}**")

    with st.form("form_novo_lancamento", clear_on_submit=True):
        valor_raw = st.text_input("Valor (R$)", placeholder="Ex: 5,00 ou 150,00")

        cat_final = cat_selecionada
        if cat_selecionada == "Outro":
            cat_especificada = st.text_input("Especifique a categoria *", placeholder="Ex: Corrida particular, Troca de óleo...")
            cat_final = cat_especificada.strip()

        descricao_input = st.text_input("Observação (Opcional)", placeholder="Ex: Posto Ipiranga, corrida longa...")

        btn_salvar = st.form_submit_button("💾 Salvar Registro", use_container_width=True, type="primary")

        if btn_salvar:
            valor_num = converter_valor(valor_raw)
            if valor_num < 0:
                st.error("Por favor, digite um valor numérico válido (ex: 5 ou 5,50).")
            elif valor_num <= 0:
                st.error("O valor informado deve ser superior a R$ 0,00.")
            elif cat_selecionada == "Outro" and not cat_final:
                st.error("Por favor, indique a categoria em 'Outro'.")
            else:
                tipo_bd = "Receita" if eh_receita else "Despesa"
                data_para_gravar = st.session_state["data_novo_lancamento"]
                inserir_registro(data_para_gravar, tipo_bd, cat_final, descricao_input.strip(), valor_num)
                st.session_state["data_novo_lancamento"] = date.today()
                st.session_state["novo_date_key_ver"] += 1
                st.session_state["msg_sucesso"] = "Lançamento salvo com sucesso!"
                st.rerun()

# --- ABA 2: GERENCIAR REGISTROS ---
with tab_gerenciar:
    if df_completo.empty:
        st.info("Nenhum lançamento registrado no banco de dados.")
    else:
        busca = st.text_input("🔍 Pesquisar nos registros:", placeholder="Filtre por categoria ou observação...").lower().strip()
        
        df_lista = df_completo.copy()
        if busca:
            df_lista = df_lista[
                df_lista["categoria"].str.lower().str.contains(busca, na=False) |
                df_lista["descricao"].str.lower().str.contains(busca, na=False)
            ]

        st.caption(f"Mostrando {min(len(df_lista), 50)} de {len(df_lista)} lançamentos")

        for _, row in df_lista.head(50).iterrows():
            item_id = int(row["id"])
            item_data = row["data"].date()
            data_str = item_data.strftime("%d/%m/%Y")
            val_formatado = formata_real(row["valor"])
            tipo_icon = "🟢" if row["tipo"] == "Receita" else "🔴"
            obs = f" - *{row['descricao']}*" if row["descricao"] else ""

            col_info, col_b1, col_b2 = st.columns([5, 1.2, 1.2])

            with col_info:
                st.markdown(f"{tipo_icon} **{data_str}** | **{row['categoria']}** | **{val_formatado}**{obs} `(ID: {item_id})`")

            with col_b1:
                if st.button("✏️ Editar", key=f"t_edit_{item_id}", use_container_width=True):
                    modal_editar_registro(item_id, item_data, row["tipo"], row["categoria"], row["descricao"], row["valor"])

            with col_b2:
                if st.button("🗑️ Excluir", key=f"t_del_{item_id}", use_container_width=True):
                    modal_excluir_registro(item_id, row["categoria"], val_formatado)

st.markdown("---")

# --- RELATÓRIOS E ANÁLISES GLOBAIS ---
df = carregar_dados()

if df.empty:
    st.info("Insira lançamentos acima para visualizar os relatórios e gráficos.")
else:
    st.subheader("📊 Relatórios e Indicadores")

    opcoes_periodo = ["Diário", "Semanal", "Mensal", "Anual", "Tudo", "Personalizado"]
    if hasattr(st, "pills"):
        periodo_selecionado = st.pills("Período de Análise:", opcoes_periodo, default="Diário")
    else:
        periodo_selecionado = st.radio("Período de Análise:", opcoes_periodo, horizontal=True)

    hoje = date.today()

    if periodo_selecionado == "Diário":
        d_inicio = hoje
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
        d_inicio = df["data"].min().date()
        d_fim = df["data"].max().date()
    else:
        min_base = df["data"].min().date()
        max_base = df["data"].max().date()
        intervalo = st.date_input("Escolha as datas:", value=(min_base, max_base))
        if isinstance(intervalo, (list, tuple)) and len(intervalo) == 2:
            d_inicio, d_fim = intervalo
        else:
            d_inicio, d_fim = min_base, max_base

    df_f = df[(df["data"].dt.date >= d_inicio) & (df["data"].dt.date <= d_fim)].copy()

    if d_inicio == d_fim:
        st.caption(f"🗓️ Exibindo dados de **{d_inicio.strftime('%d/%m/%Y')}**")
    else:
        st.caption(f"🗓️ Exibindo dados de **{d_inicio.strftime('%d/%m/%Y')}** até **{d_fim.strftime('%d/%m/%Y')}**")

    if df_f.empty:
        st.warning("Nenhum lançamento encontrado para o período selecionado.")
    else:
        tot_rec = df_f[df_f["tipo"] == "Receita"]["valor"].sum()
        tot_desp = df_f[df_f["tipo"] == "Despesa"]["valor"].sum()
        lucro = tot_rec - tot_desp
        margem = (lucro / tot_rec * 100) if tot_rec > 0 else 0.0

        dias_trabalhados = df_f["data"].dt.date.nunique()
        media_lucro_dia = (lucro / dias_trabalhados) if dias_trabalhados > 0 else 0.0

        k1, k2, k3 = st.columns(3)
        k1.metric("Faturamento Bruto", formata_real(tot_rec))
        k2.metric("Despesas Totais", formata_real(tot_desp))
        k3.metric("Lucro Líquido", formata_real(lucro), delta=f"{margem:.1f}% margem")

        st.caption(f"📅 **{dias_trabalhados}** dia(s) trabalhado(s) | Média líquida: **{formata_real(media_lucro_dia)} / dia**")

        # --- SEÇÃO DA TABELA (COM VÍRGULA NAS CASAS DECIMAIS) ---
        st.markdown("---")
        st.markdown("#### 📋 Lançamentos do Período")

        outras_rec_presentes = df_f[(df_f["tipo"] == "Receita") & (~df_f["categoria"].isin(OPCOES_RECEITA_FIXAS))]["categoria"].unique().tolist()
        outras_desp_presentes = df_f[(df_f["tipo"] == "Despesa") & (~df_f["categoria"].isin(OPCOES_DESPESA_FIXAS))]["categoria"].unique().tolist()

        opcoes_filtro_tabela = []
        for r_fix in OPCOES_RECEITA_FIXAS:
            if r_fix in df_f["categoria"].values:
                opcoes_filtro_tabela.append(r_fix)
        if outras_rec_presentes:
            opcoes_filtro_tabela.append("Outras receitas")

        for d_fix in OPCOES_DESPESA_FIXAS:
            if d_fix in df_f["categoria"].values:
                opcoes_filtro_tabela.append(d_fix)
        if outras_desp_presentes:
            opcoes_filtro_tabela.append("Outras despesas")

        cats_personalizadas = sorted(list(set(outras_rec_presentes + outras_desp_presentes)))
        for cp in cats_personalizadas:
            if cp not in opcoes_filtro_tabela:
                opcoes_filtro_tabela.append(cp)

        cats_selecionadas = st.multiselect(
            "Filtrar por Categoria(s):",
            options=opcoes_filtro_tabela,
            default=opcoes_filtro_tabela,
            placeholder="Selecione uma ou mais categorias (ex: Uber, Outras despesas...)"
        )

        cats_para_filtrar = []
        for sel in cats_selecionadas:
            if sel == "Outras receitas":
                cats_para_filtrar.extend(outras_rec_presentes)
            elif sel == "Outras despesas":
                cats_para_filtrar.extend(outras_desp_presentes)
            else:
                cats_para_filtrar.append(sel)

        df_tabela = df_f[df_f["categoria"].isin(set(cats_para_filtrar))].copy()

        if df_tabela.empty:
            st.info("Nenhum lançamento corresponde às categorias selecionadas.")
        else:
            total_entradas_filtro = df_tabela[df_tabela["tipo"] == "Receita"]["valor"].sum()
            total_saidas_filtro = df_tabela[df_tabela["tipo"] == "Despesa"]["valor"].sum()
            
            tem_rec = total_entradas_filtro > 0
            tem_desp = total_saidas_filtro > 0

            col_sub1, col_sub2 = st.columns([1, 1])
            with col_sub1:
                if tem_rec and not tem_desp:
                    st.metric("Total das Receitas Selecionadas", formata_real(total_entradas_filtro))
                elif tem_desp and not tem_rec:
                    st.metric("Total dos Custos Selecionados", formata_real(total_saidas_filtro))
                else:
                    saldo_filtro = total_entradas_filtro - total_saidas_filtro
                    st.metric("Resultado Líquido do Filtro", formata_real(saldo_filtro))
            with col_sub2:
                st.caption(f"🔍 **{len(df_tabela)}** lançamento(s) exibido(s)")
                if tem_rec and tem_desp:
                    txt_entradas = formata_real(total_entradas_filtro).replace("$", "\\$")
                    txt_saidas = formata_real(total_saidas_filtro).replace("$", "\\$")
                    st.markdown(f"🟢 Entradas: **{txt_entradas}** | 🔴 Saídas: **{txt_saidas}**")

            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)

            df_tabela["data_formatada"] = df_tabela["data"].dt.strftime("%d/%m/%Y")
            df_tabela["valor_formatado"] = df_tabela["valor"].apply(lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            
            st.dataframe(
                df_tabela[["id", "data_formatada", "tipo", "categoria", "valor_formatado", "descricao"]],
                column_config={
                    "id": "ID",
                    "data_formatada": "Data",
                    "tipo": "Tipo",
                    "categoria": "Categoria",
                    "valor_formatado": "Valor",
                    "descricao": "Observação"
                },
                use_container_width=True,
                hide_index=True
            )

            csv_data = df_tabela[["id", "data", "tipo", "categoria", "valor", "descricao"]].to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Baixar Dados da Tabela Filtrada (CSV)",
                data=csv_data,
                file_name=f"financeiro_{periodo_selecionado.lower()}_filtrado.csv",
                mime="text/csv",
                use_container_width=True
            )

        # --- SEÇÃO DE GRÁFICOS ---
        st.markdown("---")
        st.markdown("#### 📈 Desempenho no Período")
        
        delta_dias = (d_fim - d_inicio).days
        if delta_dias <= 1:
            df_f["agrup"] = df_f["data"].dt.strftime("%d/%m")
        elif delta_dias <= 31:
            df_f["agrup"] = df_f["data"].dt.strftime("%d/%m")
        elif delta_dias <= 365:
            df_f["agrup"] = df_f["data"].dt.strftime("%m/%Y")
        else:
            df_f["agrup"] = df_f["data"].dt.strftime("%Y")

        df_agrup = df_f.groupby(["agrup", "tipo"], sort=False)["valor"].sum().reset_index()

        fig_bar = px.bar(
            df_agrup,
            x="agrup",
            y="valor",
            color="tipo",
            barmode="group",
            labels={"agrup": "Data/Mês", "valor": "R$", "tipo": "Tipo"},
            color_discrete_map={"Receita": "#00CC96", "Despesa": "#EF553B"}
        )
        fig_bar.update_layout(
            margin=dict(l=10, r=10, t=15, b=25),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            xaxis_title=None
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        st.markdown("#### 📊 Distribuição por Origem e Custo")
        col_d1, col_d2 = st.columns(2)

        df_rec = df_f[df_f["tipo"] == "Receita"]
        df_desp = df_f[df_f["tipo"] == "Despesa"]

        with col_d1:
            if not df_rec.empty:
                fig_pie_rec = px.pie(
                    df_rec, 
                    names="categoria", 
                    values="valor", 
                    title="Ganhos por Origem",
                    hole=0.45
                )
                fig_pie_rec.update_traces(textposition='inside', textinfo='percent+label')
                fig_pie_rec.update_layout(showlegend=False, margin=dict(l=10, r=10, t=40, b=10))
                st.plotly_chart(fig_pie_rec, use_container_width=True)
            else:
                st.caption("Sem receitas no período.")

        with col_d2:
            if not df_desp.empty:
                fig_pie_desp = px.pie(
                    df_desp, 
                    names="categoria", 
                    values="valor", 
                    title="Custos por Categoria",
                    hole=0.45
                )
                fig_pie_desp.update_traces(textposition='inside', textinfo='percent+label')
                fig_pie_desp.update_layout(showlegend=False, margin=dict(l=10, r=10, t=40, b=10))
                st.plotly_chart(fig_pie_desp, use_container_width=True)
            else:
                st.caption("Sem despesas no período.")

components.html("""
<script>
    function travarTecladoData() {
        const doc = window.parent.document;
        const inputs = doc.querySelectorAll('div[data-testid="stDateInput"] input');
        inputs.forEach(input => {
            input.setAttribute('inputmode', 'none');
            input.setAttribute('readonly', 'true');
            input.onfocus = function() {
                input.blur();
            };
        });
    }
    travarTecladoData();
    const obs = new MutationObserver(travarTecladoData);
    obs.observe(window.parent.document.body, { childList: true, subtree: true });
</script>
""", height=0, width=0)
