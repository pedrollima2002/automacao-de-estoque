"""Automação configurável e retomável para cadastro de produtos.

O modo padrão é ``simular`` e não controla mouse, teclado ou navegador.
O envio real exige ``--modo executar --confirmar-envio`` e credenciais no .env.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import sys
import time
import webbrowser

import pandas as pd
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = PROJECT_ROOT / "data" / "produtos_exemplo.csv"
DEFAULT_CONFIG = PROJECT_ROOT / "config.example.json"
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"
DEFAULT_STATE_FILE = PROJECT_ROOT / "estado" / "progresso.json"

REQUIRED_COLUMNS = [
    "codigo",
    "marca",
    "tipo",
    "categoria",
    "preco_unitario",
    "custo",
    "obs",
]


class ValidationError(ValueError):
    """Indica dados ou configuração inválidos antes da automação."""


@dataclass(frozen=True)
class Product:
    codigo: str
    marca: str
    tipo: str
    categoria: str
    preco_unitario: str
    custo: str
    obs: str

    def form_values(self) -> list[str]:
        return [
            self.codigo,
            self.marca,
            self.tipo,
            self.categoria,
            self.preco_unitario,
            self.custo,
            self.obs,
        ]


@dataclass(frozen=True)
class AutomationConfig:
    url: str
    browser_wait_seconds: float
    login_wait_seconds: float
    submission_wait_seconds: float
    typing_interval_seconds: float
    scroll_amount: int
    login_email_position: tuple[int, int]
    product_code_position: tuple[int, int]


def _clean_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _format_number(value: object, *, row: int, column: str) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"Linha {row}: '{column}' precisa ser numérico; recebido {value!r}."
        ) from exc
    if not math.isfinite(number):
        raise ValidationError(f"Linha {row}: '{column}' precisa ser um número finito.")
    if number < 0:
        raise ValidationError(f"Linha {row}: '{column}' não pode ser negativo.")
    return f"{number:.2f}"


def load_products(csv_path: Path) -> list[Product]:
    """Lê e valida o CSV inteiro antes de qualquer ação na interface."""

    if not csv_path.is_file():
        raise ValidationError(f"Arquivo CSV não encontrado: {csv_path}")

    try:
        frame = pd.read_csv(csv_path, dtype={"codigo": "string"})
    except Exception as exc:
        raise ValidationError(f"Não foi possível ler o CSV: {exc}") from exc

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ValidationError(
            "Colunas obrigatórias ausentes: " + ", ".join(missing_columns)
        )
    if frame.empty:
        raise ValidationError("O CSV não contém produtos.")

    clean_codes = frame["codigo"].astype("string").str.strip()
    duplicate_codes = (
        clean_codes.notna()
        & clean_codes.ne("")
        & clean_codes.duplicated(keep=False)
    )
    if duplicate_codes.any():
        codes = sorted(clean_codes.loc[duplicate_codes].astype(str).unique())
        raise ValidationError("Códigos duplicados no CSV: " + ", ".join(codes[:10]))

    products: list[Product] = []
    errors: list[str] = []

    for index, record in frame.iterrows():
        row = index + 2
        try:
            codigo = _clean_text(record["codigo"])
            marca = _clean_text(record["marca"])
            tipo = _clean_text(record["tipo"])
            categoria = _clean_text(record["categoria"])
            obs = _clean_text(record["obs"])

            required_text = {
                "codigo": codigo,
                "marca": marca,
                "tipo": tipo,
                "categoria": categoria,
            }
            empty = [name for name, value in required_text.items() if not value]
            if empty:
                raise ValidationError(
                    f"Linha {row}: campos vazios: {', '.join(empty)}."
                )

            products.append(
                Product(
                    codigo=codigo,
                    marca=marca,
                    tipo=tipo,
                    categoria=categoria,
                    preco_unitario=_format_number(
                        record["preco_unitario"], row=row, column="preco_unitario"
                    ),
                    custo=_format_number(record["custo"], row=row, column="custo"),
                    obs=obs,
                )
            )
        except ValidationError as exc:
            errors.append(str(exc))

    if errors:
        preview = "\n".join(f"- {error}" for error in errors[:20])
        suffix = "" if len(errors) <= 20 else f"\n- ... e mais {len(errors) - 20} erro(s)."
        raise ValidationError(f"O CSV possui {len(errors)} erro(s):\n{preview}{suffix}")

    return products


def _position(value: object, name: str) -> tuple[int, int]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(isinstance(item, int) for item in value)
    ):
        raise ValidationError(
            f"Configuração '{name}' deve ser uma lista com dois inteiros: [x, y]."
        )
    return value[0], value[1]


def load_config(config_path: Path) -> AutomationConfig:
    if not config_path.is_file():
        raise ValidationError(f"Arquivo de configuração não encontrado: {config_path}")
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        timings = raw["timings"]
        positions = raw["positions"]
        config = AutomationConfig(
            url=str(raw["url"]).strip(),
            browser_wait_seconds=float(timings["browser_wait_seconds"]),
            login_wait_seconds=float(timings["login_wait_seconds"]),
            submission_wait_seconds=float(timings["submission_wait_seconds"]),
            typing_interval_seconds=float(timings["typing_interval_seconds"]),
            scroll_amount=int(raw["scroll_amount"]),
            login_email_position=_position(positions["login_email"], "login_email"),
            product_code_position=_position(positions["product_code"], "product_code"),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Configuração inválida: {exc}") from exc

    if not config.url.startswith(("http://", "https://")):
        raise ValidationError("A URL da configuração deve começar com http:// ou https://.")
    timing_values = [
        config.browser_wait_seconds,
        config.login_wait_seconds,
        config.submission_wait_seconds,
        config.typing_interval_seconds,
    ]
    if any(not math.isfinite(value) or value < 0 for value in timing_values):
        raise ValidationError("Os tempos da configuração devem ser números finitos e não negativos.")
    return config


def file_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_next_index(state_file: Path, csv_path: Path) -> int:
    if not state_file.exists():
        return 0
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Não foi possível ler o progresso salvo: {exc}") from exc

    if state.get("csv_fingerprint") != file_fingerprint(csv_path):
        raise ValidationError(
            "O CSV mudou desde a última execução. Use --reiniciar-progresso ou outro arquivo de estado."
        )
    next_index = state.get("next_index")
    if not isinstance(next_index, int) or next_index < 0:
        raise ValidationError("O arquivo de progresso contém um índice inválido.")
    return next_index


def save_progress(
    state_file: Path, csv_path: Path, next_index: int, last_code: str
) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "csv": str(csv_path.resolve()),
        "csv_fingerprint": file_fingerprint(csv_path),
        "next_index": next_index,
        "last_code": last_code,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    temporary = state_file.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(state_file)


def setup_logging(log_dir: Path) -> tuple[logging.Logger, Path]:
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = log_dir / f"automacao-{timestamp}.log"

    logger = logging.getLogger("automacao_estoque")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    return logger, log_path


class PyAutoGuiDriver:
    """Controla a interface somente no modo de execução real."""

    def __init__(self, config: AutomationConfig, logger: logging.Logger) -> None:
        import pyautogui

        self.pyautogui = pyautogui
        self.config = config
        self.logger = logger
        pyautogui.PAUSE = 0.35
        pyautogui.FAILSAFE = True

    def start(self, email: str, password: str) -> None:
        self.logger.info("Abrindo a página de cadastro no navegador padrão.")
        if not webbrowser.open(self.config.url, new=2):
            raise RuntimeError("O navegador padrão não pôde ser aberto.")
        time.sleep(self.config.browser_wait_seconds)

        self.pyautogui.click(*self.config.login_email_position)
        self.pyautogui.write(email, interval=self.config.typing_interval_seconds)
        self.pyautogui.press("tab")
        self.pyautogui.write(password, interval=self.config.typing_interval_seconds)
        self.pyautogui.press("tab")
        self.pyautogui.press("enter")
        time.sleep(self.config.login_wait_seconds)

    def register(self, product: Product) -> None:
        self.pyautogui.click(*self.config.product_code_position)
        for value in product.form_values():
            if value:
                self.pyautogui.write(value, interval=self.config.typing_interval_seconds)
            self.pyautogui.press("tab")
        self.pyautogui.press("enter")
        time.sleep(self.config.submission_wait_seconds)
        self.pyautogui.scroll(self.config.scroll_amount)

    def capture_error(self, log_dir: Path, code: str) -> Path:
        safe_code = re.sub(r"[^A-Za-z0-9_.-]+", "_", code)[:80] or "sem-codigo"
        path = log_dir / f"erro-{safe_code}-{datetime.now():%Y%m%d-%H%M%S}.png"
        self.pyautogui.screenshot(str(path))
        return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Valida e automatiza o cadastro de produtos a partir de um CSV."
    )
    parser.add_argument("--arquivo", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--modo", choices=["simular", "executar"], default="simular")
    parser.add_argument(
        "--confirmar-envio",
        action="store_true",
        help="Confirma conscientemente o controle da interface e o envio dos cadastros.",
    )
    parser.add_argument("--iniciar-em", type=int, help="Linha de produto inicial, começando em 1.")
    parser.add_argument("--limite", type=int, help="Quantidade máxima de produtos desta execução.")
    parser.add_argument("--estado", type=Path, default=DEFAULT_STATE_FILE)
    parser.add_argument("--reiniciar-progresso", action="store_true")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    csv_path = args.arquivo.resolve()
    config_path = args.config.resolve()
    state_file = args.estado.resolve()
    logger, log_path = setup_logging(DEFAULT_LOG_DIR)

    logger.info("Modo selecionado: %s", args.modo)
    logger.info("CSV: %s", csv_path)
    products = load_products(csv_path)
    config = load_config(config_path)
    logger.info("Validação concluída: %s produto(s).", len(products))

    if args.limite is not None and args.limite < 1:
        raise ValidationError("--limite deve ser maior que zero.")
    if args.iniciar_em is not None and args.iniciar_em < 1:
        raise ValidationError("--iniciar-em deve ser maior que zero.")

    email = ""
    password = ""
    if args.modo == "executar":
        if not args.confirmar_envio:
            raise ValidationError(
                "O modo executar exige --confirmar-envio. Rode primeiro em modo simular."
            )
        load_dotenv(PROJECT_ROOT / ".env")
        email = os.getenv("AUTOMACAO_EMAIL", "").strip()
        password = os.getenv("AUTOMACAO_SENHA", "")
        if not email or not password:
            raise ValidationError(
                "Defina AUTOMACAO_EMAIL e AUTOMACAO_SENHA no arquivo .env antes de executar."
            )
    elif args.reiniciar_progresso:
        raise ValidationError(
            "--reiniciar-progresso só pode ser usado no modo executar."
        )

    if args.reiniciar_progresso and state_file.exists():
        state_file.unlink()
        logger.info("Progresso anterior removido.")

    if args.iniciar_em is not None:
        start_index = args.iniciar_em - 1
    elif args.modo == "executar":
        start_index = load_next_index(state_file, csv_path)
    else:
        start_index = 0

    if (
        start_index == len(products)
        and args.iniciar_em is None
        and args.modo == "executar"
    ):
        logger.info("Nenhum produto pendente: o arquivo de progresso já está concluído.")
        logger.info("Log salvo em %s", log_path)
        return 0
    if start_index >= len(products):
        raise ValidationError(
            f"O início solicitado ({start_index + 1}) ultrapassa os {len(products)} produtos."
        )

    selected = products[start_index:]
    if args.limite is not None:
        selected = selected[: args.limite]

    if args.modo == "simular":
        for offset, product in enumerate(selected, start=start_index + 1):
            logger.info(
                "SIMULAÇÃO | linha=%s | codigo=%s | marca=%s | tipo=%s | preco=%s",
                offset,
                product.codigo,
                product.marca,
                product.tipo,
                product.preco_unitario,
            )
        logger.info(
            "Simulação concluída: %s produto(s). Nenhum dado foi enviado.", len(selected)
        )
        logger.info("Log salvo em %s", log_path)
        return 0

    driver = PyAutoGuiDriver(config, logger)
    driver.start(email, password)

    for index, product in enumerate(selected, start=start_index):
        try:
            logger.info(
                "CADASTRO | linha=%s/%s | codigo=%s",
                index + 1,
                len(products),
                product.codigo,
            )
            driver.register(product)
            save_progress(state_file, csv_path, index + 1, product.codigo)
            logger.info("SUCESSO | codigo=%s", product.codigo)
        except Exception:
            try:
                screenshot: Path | str = driver.capture_error(
                    DEFAULT_LOG_DIR, product.codigo
                )
            except Exception as screenshot_error:
                screenshot = "indisponível"
                logger.warning(
                    "Não foi possível capturar a tela da falha: %s", screenshot_error
                )
            logger.exception(
                "FALHA | codigo=%s | captura=%s | execução interrompida",
                product.codigo,
                screenshot,
            )
            raise

    logger.info("Execução concluída: %s produto(s) cadastrados.", len(selected))
    logger.info("Log salvo em %s", log_path)
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return run(parse_args(argv))
    except ValidationError as exc:
        print(f"ERRO DE VALIDAÇÃO: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Execução interrompida pelo usuário.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
