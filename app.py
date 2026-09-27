import streamlit as st
import pandas as pd
from datetime import date, timedelta
import plotly.express as px
from sqlalchemy import create_engine, text

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
</style>
""", unsafe_allow_html=True)

# Opções fixas
OPCOES_RECEITA_FIXAS = ["Uber", "99", "Pedágio Uber", "Particular"]
OPCOES_DESPESA_FIXAS = ["Combustível", "Lavagem", "SemParar do dia"]

OPCOES_RECEITA_FORM = OPCOES_RECEITA_FIXAS + ["Outro"]
OPCOES_DESPESA_FORM = OPCOES_DESPESA_FIXAS + ["Outro"]

# Função auxiliar para formatação em Real
def formata_real(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# Função para converter qualquer entrada de texto de valor (com ponto ou vírgula) em float válido
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

# Conexão com o Supabase via Secrets do Streamlit Cloud
raw_url = st.secrets["database"]["url"]

# Ajuste automático do driver psycopg e sslmode
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

st.title("🚗 Gestão Financeira")

df_completo = carregar_dados()

# Mensagens de alerta persistentes
if "msg_sucesso" in st.session_state:
    st.success(st.session_state.pop("msg_sucesso"))

# Separadores principais
tab_novo, tab_editar = st.tabs(["➕ Novo Lançamento", "✏️ Gerenciar Registros"])

# --- ABA 1: NOVO LANÇAMENTO ---
with tab_novo:
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        tipo_escolhido = st.radio("Tipo", ["Receita (Ganhos)", "Despesa (Custos)"], horizontal=True, key="novo_tipo")
    
    eh_receita = tipo_escolhido == "Receita (Ganhos)"
    opcoes_cat = OPCOES_RECEITA_FORM if eh_receita else OPCOES_DESPESA_FORM

    with col_t2:
        cat_selecionada = st.selectbox("Categoria / Atividade", opcoes_cat, key="novo_cat_sel")

    with st.form("form_novo_lancamento", clear_on_submit=True):
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            data_reg = st.date_input("Data", value=date.today())
        with col_f2:
            valor_raw = st.text_input("Valor (R$)", placeholder="Ex: 5,00 ou 150")

        cat_final = cat_selecionada
        if cat_selecionada == "Outro":
            cat_especificada = st.text_input("Especifique a categoria *", placeholder="Ex: Corrida fora do app, Troca de óleo...")
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
                inserir_registro(data_reg, tipo_bd, cat_final, descricao_input.strip(), valor_num)
                st.session_state["msg_sucesso"] = "Lançamento salvo com sucesso!"
                st.rerun()

# --- ABA 2: GERENCIAR REGISTROS (EDIÇÃO E EXCLUSÃO SIMPLIFICADA) ---
with tab_editar:
    if df_completo.empty:
        st.info("Nenhum lançamento registrado no banco de dados.")
    else:
        # Criação de lista limpa e legível para seleção
        df_edit = df_completo.copy()
        df_edit["rotulo"] = df_edit.apply(
            lambda r: f"ID #{r['id']} | {r['data'].strftime('%d/%m/%Y')} | {r['tipo']} | {r['categoria']} | {formata_real(r['valor'])}",
            axis=1
        )
        
        col_sel1, col_sel2 = st.columns([3, 1])
        with col_sel1:
            item_selecionado_rotulo = st.selectbox(
                "Selecione um lançamento para editar ou excluir:",
                options=df_edit["rotulo"].tolist(),
                index=0,
                key="gerenciar_select_id"
            )
        
        id_atual = int(item_selecionado_rotulo.split("#")[1].split(" ")[0])
        item_atual = df_edit[df_edit["id"] == id_atual].iloc[0]

        # Container visual destacado para a ação
        with st.container():
            st.markdown(f"#### 📝 Alterando Lançamento **ID #{id_atual}**")
            
            c_ed1, c_ed2, c_ed3 = st.columns([1, 1, 1])
            with c_ed1:
                tipo_ed = st.radio("Tipo:", ["Receita", "Despesa"], index=0 if item_atual["tipo"] == "Receita" else 1, horizontal=True)
            with c_ed2:
                data_ed = st.date_input("Data do Registro:", value=item_atual["data"].date(), key=f"d_ed_{id_atual}")
            with c_ed3:
                valor_ed_str = st.text_input("Valor (R$):", value=f"{float(item_atual['valor']):.2f}".replace(".", ","), key=f"v_ed_{id_atual}")

            # Seleção de categorias
            opcoes_ed_lista = OPCOES_RECEITA_FORM if tipo_ed == "Receita" else OPCOES_DESPESA_FORM
            cat_atual_bd = item_atual["categoria"]
            
            if cat_atual_bd in opcoes_ed_lista and cat_atual_bd != "Outro":
                idx_cat_ed = opcoes_ed_lista.index(cat_atual_bd)
                custom_cat_val = ""
            else:
                idx_cat_ed = opcoes_ed_lista.index("Outro")
                custom_cat_val = cat_atual_bd

            col_cat1, col_cat2 = st.columns(2)
            with col_cat1:
                cat_ed_sel = st.selectbox("Categoria:", opcoes_ed_lista, index=idx_cat_ed, key=f"c_ed_{id_atual}")
            with col_cat2:
                if cat_ed_sel == "Outro":
                    cat_ed_final = st.text_input("Especifique a categoria *", value=custom_cat_val, key=f"out_{id_atual}").strip()
                else:
                    cat_ed_final = cat_ed_sel

            desc_ed = st.text_input("Observação:", value=item_atual["descricao"] if item_atual["descricao"] else "", key=f"obs_{id_atual}").strip()

            st.write("")
            col_botoes1, col_botoes2 = st.columns([1, 1])

            # Botão de Atualizar
            with col_botoes1:
                if st.button("💾 Salvar Alterações", use_container_width=True, type="primary", key=f"btn_salv_{id_atual}"):
                    val_atualizado = converter_valor(valor_ed_str)
                    if val_atualizado <= 0:
                        st.error("O valor informado deve ser superior a R$ 0,00.")
                    elif cat_ed_sel == "Outro" and not cat_ed_final:
                        st.error("Informe a descrição de 'Outro'.")
                    else:
                        atualizar_registro(id_atual, data_ed, tipo_ed, cat_ed_final, desc_ed, val_atualizado)
                        st.session_state["msg_sucesso"] = f"Lançamento ID #{id_atual} atualizado com sucesso!"
                        st.rerun()

            # Área de Exclusão Direta e Clara
            with col_botoes2:
                with st.expander("🗑️ Opção de Excluir Registro"):
                    st.warning(f"Atenção: A exclusão do lançamento **ID #{id_atual} ({formata_real(item_atual['valor'])})** é irreversível.")
                    confirmar_check = st.checkbox("Confirmar exclusão definitiva", key=f"chk_del_{id_atual}")
                    if st.button("Confirmo e Quero Excluir", use_container_width=True, disabled=not confirmar_check, key=f"btn_del_{id_atual}"):
                        deletar_registro(id_atual)
                        st.session_state["msg_sucesso"] = f"Lançamento ID #{id_atual} excluído com sucesso!"
                        st.rerun()

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

        # --- SEÇÃO DA TABELA (ANTES DOS GRÁFICOS) ---
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

            # Espaçamento para evitar que botões flutuantes da tabela sobreponham o texto
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)

            df_tabela["data_formatada"] = df_tabela["data"].dt.strftime("%d/%m/%Y")
            st.dataframe(
                df_tabela[["id", "data_formatada", "tipo", "categoria", "valor", "descricao"]],
                column_config={
                    "id": "ID",
                    "data_formatada": "Data",
                    "tipo": "Tipo",
                    "categoria": "Categoria",
                    "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
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

        # --- SEÇÃO DE GRÁFICOS (DEPOIS DA TABELA) ---
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
