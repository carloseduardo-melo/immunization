"""RNF09 - rotina de manutenção que aplica a política de retenção do log.

Fica deliberadamente fora da API: nenhum endpoint pode apagar uma linha de
`log_auditoria`, então o expurgo é uma tarefa de operação do banco, executada
por quem administra o servidor, no mesmo ritmo do backup.

Toda a regra (inclusive a recusa de janelas abaixo da retenção mínima) vive em
`app.services.auditoria.expurgar_logs_antigos`, que é coberto por testes; aqui
há apenas a leitura dos argumentos e a abertura da sessão.

Uso:
    python scripts/expurgar_auditoria.py --dias 365
    python scripts/expurgar_auditoria.py --dias 90 --confirmar
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.database import SessionLocal  # noqa: E402
from app.services.auditoria import (  # noqa: E402
    RETENCAO_DIAS_MINIMA,
    expurgar_logs_antigos,
)

RETENCAO_PADRAO_DIAS = 365


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Remove do log de auditoria as linhas mais antigas que a janela "
            f"informada. A janela mínima permitida é de {RETENCAO_DIAS_MINIMA} dias."
        )
    )
    parser.add_argument(
        "--dias",
        type=int,
        default=RETENCAO_PADRAO_DIAS,
        help=f"Janela de retenção em dias (padrão: {RETENCAO_PADRAO_DIAS}).",
    )
    parser.add_argument(
        "--confirmar",
        action="store_true",
        help="Executa de fato a remoção. Sem esta flag, o script só informa a janela.",
    )
    args = parser.parse_args(argv)

    if not args.confirmar:
        print(
            f"Simulação: seriam removidos os logs com mais de {args.dias} dias. "
            "Repita com --confirmar para executar."
        )
        return 0

    db = SessionLocal()
    try:
        removidos = expurgar_logs_antigos(db, dias=args.dias)
    except ValueError as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print(f"{removidos} linha(s) de log removida(s) (retenção de {args.dias} dias).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
