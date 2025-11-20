# MAT – Maintenance Agent Bot

MAT (Maintenance Agent Tool) is an AI-powered maintenance chatbot that helps maintenance teams query equipment information, failures and KPIs in natural language.

## Features

- Answers questions about equipment, failures and maintenance KPIs (MTBF, MTTR, availability, etc.).
- Simple web interface built with Streamlit.
- Optional integration with Telegram so users can access the bot from their phones.
- Project structured with environment variables and `requirements.txt` for easy setup.

## Tech stack

- Python
- Streamlit
- LLM API (OpenAI or compatible)
- pandas
- python-dotenv
- Telegram Bot API (optional)

## Getting started

```bash
git clone https://github.com/AngelGarc06/mat-maintenance-bot.git
cd mat-maintenance-bot

python -m venv venv
venv\Scripts\activate   # on Windows
# source venv/bin/activate   # on Linux/Mac

pip install -r requirements.txt

copy .env.example .env  # create your env file with API keys

streamlit run app/main.py
