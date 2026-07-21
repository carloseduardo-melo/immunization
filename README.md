# 📚 Projeto III

> Projeto acadêmico desenvolvido para a disciplina **Projeto III**, aplicando conceitos de Engenharia de Software, Banco de Dados, Git/GitHub, CI/CD e metodologia ágil Scrum.

---

# 📖 Sobre o Projeto

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

| Ferramenta | Finalidade |
|------------|------------|
| Git | Controle de versão |
| GitHub | Repositório, Issues, Pull Requests e Code Review |
| GitHub Actions | Pipeline de CI/CD |
| Jira | Gerenciamento das Sprints e Product Backlog |
| Banco de Dados | Modelagem e Persistência |
| SQL | Scripts do Banco de Dados |
| Ferramenta de Prototipação | Protótipos das Telas |

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

| Nome                           | Função |
|------|----------------------------------------|
| CARLOS EDUARDO CRISTOVÃO DE MELO | Desenvolvedor |
| ANTONIA BRUNA SILVA DOS SANTOS | Desenvolvedora |
| FRANCISCO NUNES LOPES DA SILVA | Desenvolvedor |
| RODRIGO PEREIRA OLIVEIRA       | Desenvolvedor |

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