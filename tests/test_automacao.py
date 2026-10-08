import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from src.automacao import (
    ValidationError,
    load_config,
    load_next_index,
    load_products,
    save_progress,
)


VALID_ROWS = [
    {
        "codigo": "000001",
        "marca": "Loja Teste",
        "tipo": "Camiseta",
        "categoria": "1",
        "preco_unitario": 49.9,
        "custo": 20,
        "obs": "Teste",
    },
    {
        "codigo": "000002",
        "marca": "Loja Teste",
        "tipo": "Calca",
        "categoria": "2",
        "preco_unitario": 99.9,
        "custo": 42.5,
        "obs": "",
    },
]


class AutomationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_csv(self, rows=None) -> Path:
        path = self.directory / "produtos.csv"
        pd.DataFrame(VALID_ROWS if rows is None else rows).to_csv(path, index=False)
        return path

    def write_config(self) -> Path:
        path = self.directory / "config.json"
        path.write_text(
            json.dumps(
                {
                    "url": "https://example.com/cadastro",
                    "timings": {
                        "browser_wait_seconds": 1,
                        "login_wait_seconds": 1,
                        "submission_wait_seconds": 1,
                        "typing_interval_seconds": 0.01,
                    },
                    "scroll_amount": -500,
                    "positions": {
                        "login_email": [100, 200],
                        "product_code": [300, 400],
                    },
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_load_products_preserves_code_and_formats_numbers(self) -> None:
        products = load_products(self.write_csv())
        self.assertEqual(products[0].codigo, "000001")
        self.assertEqual(products[0].preco_unitario, "49.90")
        self.assertEqual(products[1].custo, "42.50")

    def test_rejects_missing_column(self) -> None:
        rows = [{key: value for key, value in VALID_ROWS[0].items() if key != "custo"}]
        with self.assertRaisesRegex(ValidationError, "custo"):
            load_products(self.write_csv(rows))

    def test_rejects_duplicate_codes(self) -> None:
        rows = [VALID_ROWS[0], {**VALID_ROWS[1], "codigo": "000001"}]
        with self.assertRaisesRegex(ValidationError, "Códigos duplicados"):
            load_products(self.write_csv(rows))

    def test_rejects_negative_price(self) -> None:
        rows = [{**VALID_ROWS[0], "preco_unitario": -1}]
        with self.assertRaisesRegex(ValidationError, "não pode ser negativo"):
            load_products(self.write_csv(rows))

    def test_rejects_missing_numeric_value(self) -> None:
        rows = [{**VALID_ROWS[0], "custo": None}]
        with self.assertRaisesRegex(ValidationError, "número finito"):
            load_products(self.write_csv(rows))

    def test_loads_valid_config(self) -> None:
        config = load_config(self.write_config())
        self.assertEqual(config.login_email_position, (100, 200))
        self.assertEqual(config.product_code_position, (300, 400))

    def test_progress_resumes_same_csv(self) -> None:
        csv_path = self.write_csv()
        state_path = self.directory / "estado.json"
        save_progress(state_path, csv_path, 1, "000001")
        self.assertEqual(load_next_index(state_path, csv_path), 1)

    def test_progress_rejects_changed_csv(self) -> None:
        csv_path = self.write_csv()
        state_path = self.directory / "estado.json"
        save_progress(state_path, csv_path, 1, "000001")
        csv_path.write_text(csv_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "O CSV mudou"):
            load_next_index(state_path, csv_path)


if __name__ == "__main__":
    unittest.main()
