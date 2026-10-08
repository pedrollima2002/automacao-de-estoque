"""Mostra a posição atual do mouse após uma contagem regressiva."""

import argparse
import time

import pyautogui


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture coordenadas para preencher config.example.json."
    )
    parser.add_argument(
        "--segundos",
        type=int,
        default=5,
        help="Tempo para posicionar o mouse antes da captura (padrão: 5).",
    )
    args = parser.parse_args()

    if args.segundos < 1:
        parser.error("--segundos deve ser maior que zero")

    print("Posicione o mouse no campo desejado.")
    for remaining in range(args.segundos, 0, -1):
        print(f"Captura em {remaining}...", flush=True)
        time.sleep(1)

    position = pyautogui.position()
    print(f"Posição capturada: [{position.x}, {position.y}]")


if __name__ == "__main__":
    main()
