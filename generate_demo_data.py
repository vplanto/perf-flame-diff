import os
import random


def generate_profile(filename, scenario="baseline"):
    """
    Generates a synthetic collapsed stack profile.
    Format: func;func;func count
    """
    print(f"Generating {filename} ({scenario})...")

    with open(filename, "w") as f:
        # 1. Background Noise (OS/Kernel) - Stable
        # Це "сірий" фон, який не змінюється
        for _ in range(50):
            f.write(f"kernel;sys_call;do_sys_poll {random.randint(10, 20)}\n")
            f.write(f"kernel;scheduler;schedule {random.randint(5, 15)}\n")

        # 2. Main Application Logic - Stable
        # Основний потік, який працює нормально
        for i in range(100):
            val = random.randint(50, 100)
            f.write(
                f"com/app/Server;com/app/RequestWorker;handleRequest;validateToken {val}\n"
            )
            f.write(
                f"com/app/Server;com/app/RequestWorker;handleRequest;businessLogic {val * 2}\n"
            )

        # 3. THE REGRESSION (JSON Parsing)
        # У сценарії "regression" ми збільшуємо навантаження на JSON парсер у 5 разів
        if scenario == "baseline":
            # Швидкий парсинг (норма)
            f.write(
                "com/app/Server;com/app/RequestWorker;parseJson;JacksonParser 1500\n"
            )
            f.write("com/app/Server;com/app/RequestWorker;parseJson;GsonParser 200\n")
        else:
            # РЕГРЕСІЯ: Хтось додав повільний regex у парсинг
            # Це створить величезний ЧЕРВОНИЙ блок
            f.write(
                "com/app/Server;com/app/RequestWorker;parseJson;JacksonParser 1600\n"
            )  # Трохи виросло
            f.write("com/app/Server;com/app/RequestWorker;parseJson;GsonParser 200\n")
            # Ось проблема:
            f.write(
                "com/app/Server;com/app/RequestWorker;parseJson;CustomRegexValidator;slowMatch 5000\n"
            )

        # 4. Optimization (Green Zone)
        # У "regression" ми оптимізували логування (воно зникло)
        # Це створить ЗЕЛЕНИЙ блок (було -> стало 0)
        if scenario == "baseline":
            f.write("com/app/Server;com/app/Logger;logDebug;writeToDisk 1000\n")
        else:
            # Логування вимкнули, семплів немає (або дуже мало)
            f.write("com/app/Server;com/app/Logger;logDebug;writeToDisk 10\n")


# Створення папки
os.makedirs("demo_data", exist_ok=True)

# Генерація файлів
generate_profile("demo_data/baseline.txt", "baseline")
generate_profile("demo_data/regression.txt", "regression")

print("Done! Files created in demo_data/")
