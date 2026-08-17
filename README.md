# 💉 Caminhos da Imunização

> Plataforma de inteligência geográfica e epidemiológica para análise do deslocamento vacinal no Estado do Ceará, desenvolvida como atividade da disciplina de **Projeto III** (Engenharia de Software).

>login:admin@imunizacao.local
>senha:Admin@123

---

# 📖 O Projeto

O **Caminhos da Imunização** nasce da necessidade de compreender o fluxo intermunicipal de pacientes em busca de vacinas. O sistema processa uma base massiva de dados de vacinação (mais de 4,8 milhões de registros de origem) para fornecer aos gestores públicos de saúde um panorama claro de onde as vacinas estão sendo aplicadas versus a residência real dos pacientes.

Este repositório contém o código-fonte (Backend em FastAPI e Frontend em Streamlit) e a organização do desenvolvimento do projeto. O gerenciamento das atividades é realizado via **Jira**, utilizando a metodologia ágil **Scrum**, enquanto o **GitHub** é utilizado para versionamento, Pull Requests e pipelines de CI/CD.

**O Caminhos da Imunização em Resumo**
Uma plataforma de inteligência de dados em saúde (desenvolvida em Python, FastAPI e Streamlit) que mapeia o fluxo intermunicipal de pacientes em busca de vacinas no estado do Ceará.

**O Problema que Resolve**
O "deslocamento vacinal". Pacientes vacinam-se fora das suas cidades de residência, gerando escassez de doses em alguns locais (**municípios-polo**) e mascarando as taxas de cobertura noutros (**municípios de evasão**). O sistema entrega este diagnóstico mastigado aos gestores públicos.

**Destaques Técnicos e Funcionais:**

-

**Processamento Massivo (ETL):** Absorve quase 5 milhões de registos em CSV e comprime o volume no banco de dados em 62% através de agregação inteligente, preservando o anonimato dos pacientes (LGPD).

-

**Inteligência Autónoma:** O próprio sistema cruza a cidade de residência com a de aplicação para calcular deslocamentos, e isola automaticamente dados biologicamente impossíveis (ex.: idades > 110 anos) para não contaminar as estatísticas.

-

**Alta Performance:** Recorre a _Views Materializadas_ no PostgreSQL para garantir que os dashboards analíticos carreguem milhões de dados agregados em menos de 2 segundos.

-

**Segurança e Transparência:** Nenhuma eliminação de dados é física (apenas lógica). Toda a alteração gera um log de auditoria invisível e imutável, essencial para sistemas governamentais.

---

# 🎯 Objetivos do Sistema

### Objetivo Principal

Desenvolver uma ferramenta analítica e operacional que permita aos gestores de saúde do Ceará monitorar o deslocamento vacinal, auxiliando na tomada de decisão sobre distribuição de imunobiológicos e políticas públicas de saúde.

### Objetivos Específicos (Escopo de Negócio)

De acordo com os requisitos estabelecidos, o sistema deve:

- **Gestão de Dados:** Permitir que gestores consultem e gerenciem (CRUD) registros de vacinação, municípios e vacinas de forma segura.
- **Análise de Mobilidade:** Identificar automaticamente o deslocamento vacinal, mapeando **municípios-polo** (que recebem volume relevante de pacientes de fora) e **municípios de evasão** (cujos residentes se vacinam em outros locais).
- **Painéis Analíticos:** Visualizar dashboards de fluxo intermunicipal, sazonalidade e uso de imunobiológicos de alta complexidade.
- **Saneamento de Dados:** Sinalizar automaticamente registros biologicamente inconsistentes (ex: idades > 110 anos) e gerar alertas de completude de dados.
- **Auditoria e Segurança:** Manter um log de auditoria imutável de todas as alterações feitas no sistema, garantindo a rastreabilidade das ações dos usuários.

---

# 📚 Projeto III

> Projeto acadêmico desenvolvido para a disciplina **Projeto III**, aplicando conceitos de Engenharia de Software, Banco de Dados, Git/GitHub, CI/CD e metodologia ágil Scrum.

---

# 📖 Sobre o repositório do Projeto

Este repositório contém o código-fonte e a organização do desenvolvimento do projeto da disciplina **Projeto III**.

O gerenciamento das atividades será realizado utilizando **Jira**, enquanto o **GitHub** será utilizado para versionamento do código, gerenciamento de Issues, Pull Requests, GitHub Actions e integração contínua.

---

# 🎯 Objetivos

- Desenvolver uma solução para o problema proposto.
- Aplicar boas práticas de Engenharia de Software.
- Utilizar Scrum durante todo o desenvolvimento.
- Automatizar processos através de CI/CD.
- Trabalhar de forma colaborativa utilizando Git e GitHub.

---

# 🛠️ Ferramentas Utilizadas

| Ferramenta                 | Finalidade                                       |
| -------------------------- | ------------------------------------------------ |
| Git                        | Controle de versão                               |
| GitHub                     | Repositório, Issues, Pull Requests e Code Review |
| GitHub Actions             | Pipeline de CI/CD                                |
| Jira                       | Gerenciamento das Sprints e Product Backlog      |
| Banco de Dados             | Modelagem e Persistência                         |
| SQL                        | Scripts do Banco de Dados                        |
| Ferramenta de Prototipação | Protótipos das Telas                             |

---

# 📋 Gerenciamento do Projeto

## Jira

O Jira será utilizado para:

- Product Backlog
- Sprint Backlog
- Planejamento das Sprints
- User Stories
- Tarefas
- Definição de responsáveis
- Sprint Review
- Sprint Retrospective
- Acompanhamento do progresso

---

## GitHub

O GitHub será utilizado para:

- Hospedagem do código-fonte
- Controle de versão
- Gerenciamento de Issues
- Pull Requests
- Code Review
- Organização das Branches
- GitHub Actions (CI/CD)

---

# 🌿 Estratégia de Branches

```text
main
├── develop (opcional)
├── feature/nome-da-feature
├── fix/nome-do-bug
├── docs/nome-documentacao
└── hotfix/nome-do-ajuste
```

---

# 🔒 Proteção da Branch Main

A branch **main** permanecerá protegida durante todo o desenvolvimento.

### Regras

- ❌ Push direto proibido
- ✅ Alterações apenas por Pull Request
- ✅ Aprovação obrigatória para merge
- ✅ CI obrigatório antes do merge
- ✅ Histórico preservado

---

# 🔄 Fluxo de Desenvolvimento

```text
Jira
 │
 ▼
Criar Issue
 │
 ▼
Criar Branch
 │
 ▼
Desenvolvimento
 │
 ▼
Commit
 │
 ▼
Push
 │
 ▼
Pull Request
 │
 ▼
GitHub Actions (CI)
 │
 ▼
Code Review
 │
 ▼
Merge
 │
 ▼
Main
```

---

# ⚙️ Integração Contínua (CI)

O projeto utilizará **GitHub Actions** para automatizar o processo de validação do código.

A pipeline poderá executar automaticamente:

- Checkout do projeto
- Instalação de dependências
- Build da aplicação
- Execução de testes
- Validação de qualidade do código (Lint)
- Verificação de erros de compilação

Toda Pull Request deverá passar pela pipeline antes de ser aprovada.

---

# 🚀 Entrega Contínua (CD)

A pipeline de CD poderá ser utilizada para:

- Publicação automática da aplicação
- Deploy em ambiente de homologação
- Deploy em ambiente de produção (quando aplicável)
- Geração de artefatos da aplicação

---

# 👥 Integrantes da Equipe

| Nome                             | Função         |
| -------------------------------- | -------------- |
| CARLOS EDUARDO CRISTOVÃO DE MELO | Desenvolvedor  |
| ANTONIA BRUNA SILVA DOS SANTOS   | Desenvolvedora |
| FRANCISCO NUNES LOPES DA SILVA   | Desenvolvedor  |
| RODRIGO PEREIRA OLIVEIRA         | Desenvolvedor  |

---

# 📝 Padrão de Commits

O projeto seguirá o padrão **Conventional Commits**.

```text
feat: nova funcionalidade

fix: correção de bug

docs: documentação

style: formatação

refactor: refatoração

test: testes

chore: manutenção

ci: alterações na pipeline

build: alterações de build
```

---

# 📄 Licença

Este projeto foi desenvolvido exclusivamente para fins acadêmicos como atividade da disciplina **Projeto III**.
