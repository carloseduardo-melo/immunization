import pandas as pd
import uuid
import os
import time
from sqlalchemy import create_engine, text, String, Integer, Boolean
from dotenv import load_dotenv

# 1. Carregar Variáveis de Ambiente e Configurar Conexão
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("A variável DATABASE_URL não foi encontrada no ficheiro .env")

# Criação do motor do SQLAlchemy
engine = create_engine(DATABASE_URL)

def processar_etl():
    inicio_tempo = time.time()
    print("A iniciar a Extração, Transformação e Carga (ETL)...")

    caminho_csv = os.path.join(os.path.dirname(__file__), 'vacinacao_ce_consolidado.csv')
    
    # Tamanho do lote (100.000 linhas por vez otimiza o uso de CPU e RAM)
    tamanho_chunk = 100000 
    
    # Lista para guardar os dataframes reduzidos (agregados)
    chunks_agregados = []
    
    # Estruturas para extrair Municípios e Vacinas únicos
    municipios_unicos = pd.DataFrame()
    vacinas_unicas = pd.DataFrame()

    print("Passo 1: Leitura em Chunks e Transformação Vetorizada...")
    # O parâmetro low_memory=False evita avisos de tipos mistos no CSV
    for i, chunk in enumerate(pd.read_csv(caminho_csv, chunksize=tamanho_chunk, low_memory=False)):
        
        # ---------------------------------------------------------
        # PREPARAÇÃO BÁSICA E PRESERVAÇÃO DE NULOS
        # ---------------------------------------------------------
        # Ajuste os nomes das colunas abaixo conforme o cabeçalho exato do seu CSV
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
        # RN02 & RN03: Atribuição do status_dado
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
        # Municípios
        mun_vacina = chunk[['municipio_vacina_id', 'municipio_vacina_nome']].rename(columns={'municipio_vacina_id': 'id_ibge', 'municipio_vacina_nome': 'nome'})
        mun_res = chunk[['municipio_residencia_id', 'municipio_residencia_nome']].rename(columns={'municipio_residencia_id': 'id_ibge', 'municipio_residencia_nome': 'nome'})
        municipios_unicos = pd.concat([municipios_unicos, mun_vacina, mun_res]).dropna(subset=['id_ibge']).drop_duplicates(subset=['id_ibge'])

        # Vacinas
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
        
        # O parâmetro dropna=False é fundamental para preservar os NULLs (Critério de Aceite)
        chunk_agrupado = chunk.groupby(colunas_agrupamento, dropna=False)['quantidade'].sum().reset_index()
        chunks_agregados.append(chunk_agrupado)

        print(f"   Lote {i+1} processado. Linhas originais: {len(chunk)} -> Linhas agregadas: {len(chunk_agrupado)}")

    print("\nPasso 2: Consolidação Final (Merge dos Chunks)...")
    df_consolidado = pd.concat(chunks_agregados)
    df_consolidado = df_consolidado.groupby(colunas_agrupamento, dropna=False)['quantidade'].sum().reset_index()
    print(f"   Volume final reduzido para {len(df_consolidado)} linhas de negócio únicas.")

    print("\nPasso 3: Carga (Load) nas Tabelas do PostgreSQL...")
    with engine.begin() as conn:
        # 3.1 Carregar Municípios
        print("   A carregar Municípios...")
        municipios_unicos['uf'] = 'CE' # Padrão conforme arquitetura
        municipios_unicos.to_sql('municipios', con=conn, if_exists='append', index=False)

        # 3.2 Carregar Vacinas
        print("   A carregar Vacinas...")
        vacinas_unicas.to_sql('vacinas', con=conn, if_exists='append', index=False)
        
        # Recupera os IDs (SERIAL) das vacinas recém inseridas para fazer o relacionamento
        vacinas_db = pd.read_sql("SELECT id, nome FROM vacinas", con=conn)
        mapa_vacinas = dict(zip(vacinas_db['nome'], vacinas_db['id']))

        # 3.3 Relacionar Vacinas no DataFrame consolidado
        df_consolidado['vacina_id'] = df_consolidado['vacina_nome'].map(mapa_vacinas)
        df_consolidado = df_consolidado.drop(columns=['vacina_nome'])

        # 3.4 O PostgreSQL gera o UUID automaticamente pelo server_default
        print("   A preparar Registros de Vacinação...")
        
        # Converte a data para o formato datetime do Pandas compatível com SQL
        df_consolidado['data_vacinacao'] = pd.to_datetime(df_consolidado['data_vacinacao'], errors='coerce')

        # Remova o campo de ID gerado localmente para permitir o UUID do banco de dados
        if 'id' in df_consolidado.columns:
            df_consolidado = df_consolidado.drop(columns=['id'])

        # Normaliza os tipos antes da inserção final
        df_consolidado['municipio_residencia_id'] = df_consolidado['municipio_residencia_id'].apply(normalizar_ibge)
        df_consolidado['municipio_vacina_id'] = df_consolidado['municipio_vacina_id'].apply(normalizar_ibge)
        df_consolidado['quantidade'] = df_consolidado['quantidade'].astype('int64')
        df_consolidado['idade'] = pd.to_numeric(df_consolidado['idade'], errors='coerce').astype('Int64')
        df_consolidado['vacina_id'] = pd.to_numeric(df_consolidado['vacina_id'], errors='coerce').astype('Int64')

        # 3.5 Carga Massiva Final (Batch Insert) otimizada
        print("   A injetar Doses Aplicadas no Banco de Dados (isto pode demorar alguns minutos)...")
        df_consolidado.to_sql(
            'registros_vacinacao', 
            con=conn, 
            if_exists='append', 
            index=False, 
            method='multi', # Força a inserção em múltiplos VALUES
            chunksize=5000,  # Tamanho ideal para o buffer do PostgreSQL
            dtype={
                'municipio_residencia_id': String(7),
                'municipio_vacina_id': String(7),
                'vacina_id': Integer,
                'quantidade': Integer,
                'idade': Integer,
                'teve_deslocamento': Boolean,
                'status_dado': String(25)
            }
        )

    tempo_total = round((time.time() - inicio_tempo) / 60, 2)
    print(f"\n✅ ETL Concluído com Sucesso em {tempo_total} minutos!")

if __name__ == '__main__':
    processar_etl()