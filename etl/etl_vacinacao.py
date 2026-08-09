import pandas as pd
import uuid
import os
import time
import logging
from sqlalchemy import create_engine, text, String, Integer, Boolean
from dotenv import load_dotenv

# 1. Configuração do Log de Execução do ETL (Critério de Aceite)
log_path = os.path.join(os.path.dirname(__file__), 'etl_execucao.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_path, encoding='utf-8'),
        logging.StreamHandler() # Exibe no terminal simultaneamente
    ]
)

# 2. Carregar Variáveis de Ambiente e Configurar Conexão
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    mensagem = "A variável DATABASE_URL não foi encontrada no ficheiro .env"
    logging.error(mensagem)
    raise ValueError(mensagem)

# Criação do motor do SQLAlchemy
engine = create_engine(DATABASE_URL)

def garantir_tabelas_alvo(conn):
    logging.info("   Garantindo o esquema das tabelas alvo no PostgreSQL...")
    conn.execute(text("DROP TABLE IF EXISTS registros_vacinacao CASCADE;"))
    conn.execute(text("DROP TABLE IF EXISTS vacinas CASCADE;"))
    conn.execute(text("DROP TABLE IF EXISTS municipios CASCADE;"))

    conn.execute(text("""
        CREATE TABLE municipios (
            id_ibge VARCHAR(7) PRIMARY KEY,
            nome VARCHAR(150) NOT NULL,
            uf VARCHAR(2) NOT NULL,
            ativo BOOLEAN NOT NULL DEFAULT TRUE
        )
    """))

    conn.execute(text("""
        CREATE TABLE vacinas (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(150) UNIQUE NOT NULL,
            alta_complexidade BOOLEAN NOT NULL DEFAULT FALSE,
            ativo BOOLEAN NOT NULL DEFAULT TRUE
        )
    """))

    conn.execute(text("""
        CREATE TABLE registros_vacinacao (
            data_vacinacao DATE NOT NULL,
            idade SMALLINT,
            vacina_id INTEGER,
            municipio_residencia_id VARCHAR(7),
            municipio_vacina_id VARCHAR(7) NOT NULL,
            teve_deslocamento BOOLEAN,
            quantidade INTEGER NOT NULL DEFAULT 1,
            status_dado VARCHAR(30) NOT NULL DEFAULT 'VALIDO'
        )
    """))


def processar_etl():
    inicio_tempo = time.time()
    logging.info("🚀 A iniciar a Extração, Transformação e Carga (ETL)...")

    caminho_csv = os.path.join(os.path.dirname(__file__), 'vacinacao_ce_consolidado.csv')
    
    # Tamanho do lote (100.000 linhas por vez otimiza o uso de CPU e RAM)
    tamanho_chunk = 100000 
    
    # Lista para guardar os dataframes reduzidos (agregados)
    chunks_agregados = []
    
    # Estruturas para extrair Municípios e Vacinas únicos
    municipios_unicos = pd.DataFrame()
    vacinas_unicas = pd.DataFrame()

    # Variável para rastrear o número exato de linhas do CSV
    total_linhas_csv = 0

    logging.info("📊 Passo 1: Leitura em Chunks e Transformação Vetorizada...")
    # O parâmetro low_memory=False evita avisos de tipos mistos no CSV
    for i, chunk in enumerate(pd.read_csv(caminho_csv, chunksize=tamanho_chunk, low_memory=False)):
        
        # Contabiliza as linhas extraídas na origem
        total_linhas_csv += len(chunk)

        # ---------------------------------------------------------
        # PREPARAÇÃO BÁSICA E PRESERVAÇÃO DE NULOS
        # ---------------------------------------------------------
        colunas_map = {
            'cod_ibge_residencia': 'municipio_residencia_id',
            'municipio_residencia': 'municipio_residencia_nome',
            'cod_ibge_vacina': 'municipio_vacina_id',
            'municipio_vacina': 'municipio_vacina_nome',
            'data_vacinacao': 'data_vacinacao',
            'nome_vacina': 'vacina_nome'
        }
        chunk = chunk.rename(columns=colunas_map)

        def normalizar_ibge(valor):
            if pd.isna(valor):
                return None
            try:
                return str(int(valor))
            except (ValueError, TypeError):
                texto = str(valor).strip()
                return texto if texto else None

        chunk['municipio_residencia_id'] = chunk['municipio_residencia_id'].apply(normalizar_ibge)
        chunk['municipio_vacina_id'] = chunk['municipio_vacina_id'].apply(normalizar_ibge)

        # ---------------------------------------------------------
        # APLICAÇÃO DAS REGRAS DE NEGÓCIO (RN01, RN02, RN03)
        # ---------------------------------------------------------
        chunk['status_dado'] = 'VALIDO'
        
        # RN02: Sem residência -> DESLOCAMENTO_INDETERMINADO
        chunk.loc[chunk['municipio_residencia_id'].isnull(), 'status_dado'] = 'DESLOCAMENTO_INDETERMINADO'
        
        # RN03: Idade < 0 ou > 110 -> DADO_INCONSISTENTE
        chunk['idade'] = pd.to_numeric(chunk['idade'], errors='coerce')
        chunk.loc[(chunk['idade'] < 0) | (chunk['idade'] > 110), 'status_dado'] = 'DADO_INCONSISTENTE'

        # RN01: Cálculo automático do Deslocamento
        chunk['teve_deslocamento'] = chunk['municipio_residencia_id'] != chunk['municipio_vacina_id']
        chunk['teve_deslocamento'] = chunk['teve_deslocamento'].astype('boolean')
        chunk.loc[chunk['municipio_residencia_id'].isnull(), 'teve_deslocamento'] = pd.NA

        # ---------------------------------------------------------
        # EXTRAÇÃO DE DIMENSÕES (Municípios e Vacinas)
        # ---------------------------------------------------------
        mun_vacina = chunk[['municipio_vacina_id', 'municipio_vacina_nome']].rename(columns={'municipio_vacina_id': 'id_ibge', 'municipio_vacina_nome': 'nome'})
        mun_res = chunk[['municipio_residencia_id', 'municipio_residencia_nome']].rename(columns={'municipio_residencia_id': 'id_ibge', 'municipio_residencia_nome': 'nome'})
        municipios_unicos = pd.concat([municipios_unicos, mun_vacina, mun_res]).dropna(subset=['id_ibge']).drop_duplicates(subset=['id_ibge'])

        vac = chunk[['vacina_nome']].dropna().rename(columns={'vacina_nome': 'nome'})
        vacinas_unicas = pd.concat([vacinas_unicas, vac]).drop_duplicates(subset=['nome'])

        # ---------------------------------------------------------
        # RN04: AGREGAÇÃO DE LINHAS IDÊNTICAS (Redução do volume)
        # ---------------------------------------------------------
        chunk['quantidade'] = 1
        colunas_agrupamento = [
            'data_vacinacao', 'idade', 'vacina_nome', 
            'municipio_residencia_id', 'municipio_vacina_id', 
            'teve_deslocamento', 'status_dado'
        ]
        
        chunk_agrupado = chunk.groupby(colunas_agrupamento, dropna=False)['quantidade'].sum().reset_index()
        chunks_agregados.append(chunk_agrupado)

        logging.info(f"   Lote {i+1} processado. Linhas originais: {len(chunk)} -> Linhas agregadas: {len(chunk_agrupado)}")

    logging.info(f"Fim da leitura. Total de linhas lidas do CSV: {total_linhas_csv}")

    logging.info("⚙️ Passo 2: Consolidação Final (Merge dos Chunks)...")
    df_consolidado = pd.concat(chunks_agregados)
    df_consolidado = df_consolidado.groupby(colunas_agrupamento, dropna=False)['quantidade'].sum().reset_index()
    logging.info(f"   Volume final reduzido para {len(df_consolidado)} linhas de negócio únicas.")

    logging.info("💾 Passo 3: Carga (Load) nas Tabelas do PostgreSQL...")
    
    # Bloco try...except com engine.begin() garante o ROLLBACK automático em caso de erro
    try:
        with engine.begin() as conn:
            garantir_tabelas_alvo(conn)

            logging.info("   A carregar Municípios...")
            municipios_unicos['uf'] = 'CE' 
            municipios_unicos.to_sql('municipios', con=conn, if_exists='append', index=False)

            logging.info("   A carregar Vacinas...")
            vacinas_unicas.to_sql('vacinas', con=conn, if_exists='append', index=False)
            
            vacinas_db = pd.read_sql("SELECT id, nome FROM vacinas", con=conn)
            mapa_vacinas = dict(zip(vacinas_db['nome'], vacinas_db['id']))

            df_consolidado['vacina_id'] = df_consolidado['vacina_nome'].map(mapa_vacinas)
            df_consolidado = df_consolidado.drop(columns=['vacina_nome'])

            logging.info("   A preparar Registros de Vacinação...")
            df_consolidado['data_vacinacao'] = pd.to_datetime(df_consolidado['data_vacinacao'], errors='coerce')

            if 'id' in df_consolidado.columns:
                df_consolidado = df_consolidado.drop(columns=['id'])

            df_consolidado['municipio_residencia_id'] = df_consolidado['municipio_residencia_id'].apply(normalizar_ibge)
            df_consolidado['municipio_vacina_id'] = df_consolidado['municipio_vacina_id'].apply(normalizar_ibge)
            df_consolidado['quantidade'] = df_consolidado['quantidade'].astype('int64')
            df_consolidado['idade'] = pd.to_numeric(df_consolidado['idade'], errors='coerce').astype('Int64')
            df_consolidado['vacina_id'] = pd.to_numeric(df_consolidado['vacina_id'], errors='coerce').astype('Int64')

            logging.info("   A injetar Doses Aplicadas no Banco de Dados (isto pode demorar alguns minutos)...")
            tamanho_lote = 1000
            for inicio in range(0, len(df_consolidado), tamanho_lote):
                lote = df_consolidado.iloc[inicio:inicio + tamanho_lote]
                lote.to_sql(
                    'registros_vacinacao',
                    con=conn,
                    if_exists='append',
                    index=False,
                    method='multi',
                    chunksize=1000,
                    dtype={
                        'municipio_residencia_id': String(7),
                        'municipio_vacina_id': String(7),
                        'vacina_id': Integer,
                        'quantidade': Integer,
                        'idade': Integer,
                        'teve_deslocamento': Boolean,
                        'status_dado': String(30)
                    }
                )

            # ---------------------------------------------------------
            # PASSO 4: VALIDAÇÃO DE INTEGRIDADE PÓS-CARGA
            # ---------------------------------------------------------
            logging.info("🔍 Passo 4: A executar validação de integridade...")
            
            # Soma a coluna 'quantidade' diretamente no PostgreSQL
            query_validacao = text("SELECT COALESCE(SUM(quantidade), 0) FROM registros_vacinacao;")
            total_banco = conn.execute(query_validacao).scalar()

            # Compara com o total de linhas rastreadas no passo 1
            if total_banco != total_linhas_csv:
                erro_msg = (
                    f"REJEIÇÃO DA CARGA: Inconsistência detetada! "
                    f"O total de linhas lidas no CSV ({total_linhas_csv}) é diferente "
                    f"da soma das quantidades no banco de dados ({total_banco})."
                )
                logging.error(f"❌ {erro_msg}")
                # Levantar esta exceção aciona o ROLLBACK imediato das inserções no PostgreSQL
                raise ValueError(erro_msg)
            
            logging.info(f"✅ VALIDAÇÃO COM SUCESSO: A soma no banco ({total_banco}) corresponde exatamente a 100% das linhas do CSV.")

    except Exception as e:
        logging.error("🚨 Ocorreu um erro crítico durante a carga. Transação revertida (ROLLBACK efetuado).")
        logging.error(str(e))
        raise

    tempo_total = round((time.time() - inicio_tempo) / 60, 2)
    logging.info(f"🚀 Processo finalizado com Sucesso em {tempo_total} minutos!")

if __name__ == '__main__':
    processar_etl()