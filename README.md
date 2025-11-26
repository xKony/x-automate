![alt text](https://img.shields.io/badge/python-3.10%2B-blue)
![alt text](https://img.shields.io/badge/license-MIT-green)
![alt text](https://img.shields.io/badge/status-Active-success)

# 🤖 AI-Powered X (Twitter) User Simulator

A robust, Object-Oriented Python application that simulates human behavior on X (_formerly Twitter_). This project uses [`nodriver`](https://github.com/ultrafunkamsterdam/nodriver) for undetected browser automation and [Mistral AI](https://mistral.ai/) to generate context-aware replies and posts.

This is a portfolio project demonstrating Asynchronous Programming (yet again), OOP Principles, and LLM Integration.

# ✨ Features

Browser Automation: Uses `nodriver` (undetected-chromedriver) to bypass bot detection mechanisms.

- LLM Integration: Powered by Mistral AI to generate human-like tweets, replies, and quotes.
- Probabilistic Actions: Simulates organic behavior using configurable probabilities for:
  - Likes
  - Reposts
  - Replies
  - Quote Tweets
- Session Management: Handles cookies and authentication tokens to maintain login sessions.
- OOP Architecture: Modular design using BaseBrowser, XBrowser, and UserSimulator classes.
- Headless Mode: Configurable support for running in the background.

# 📂 Project Structure

    ├── config.py           # Global configuration settings (probabilities, paths)
    ├── main.py             # Entry point of the application
    ├── .env                # Secrets and API keys
    ├── LLM/
    │   └── mistral_client.py   # Wrapper for Mistral AI interactions
    │   └── prompts/default_prompt      # Prompt for API call
    ├── x_handling/
    │   ├── x_browser.py        # X-specific browser logic (inherits BaseBrowser)
    │   └── user_simulator.py   # Logic for user behavior simulation
    ├── cookies/
    │   ├── auth_tokens.txt     # File for X auth_tokens (one per line)
    │   └── cookies.json        # Saves activity metrics for each account
    └── utils/
        ├── base_browser.py     # Base class for browser automation
        └── logger.py           # Custom logging configuration

# 🚀 Installation

### Prerequisites

- Python 3.10 or higher
- Google Chrome (installed on the system)

## 1. Clone the Repository

```bash
git clone https://github.com/xKony/x-automate.git
cd x-automate
```

## 2. Install Dependencies

```bash
pip install -r requirements.txt
```

## 3. Environment Setup (.env file)

```Ini
MISTRAL_API_KEY=your_actual_api_key_here
```

[Get your own API key here (need Mistral account)](https://console.mistral.ai/home?workspace_dialog=apiKeys)

## 4. Configuration

- Ensure your config.py is set up with your desired simulation parameters.
- Put your auth tokens in cookies/auth_tokens.txt one at a line

## 💻 Usage

```bash
python main.py
```

The bot will launch the browser, load your auth tokens, and begin the simulation loop based on the logic defined in `UserSimulator`.

## 🧠 How It Works

This project utilizes Object-Oriented Programming to ensure code scalability and maintainability:

- `BaseBrowser`: Handles core browser functions (starting drivers, page navigation, scrolling).

- `XBrowser` (Inherits BaseBrowser): Extends functionality specifically for X.com DOM elements (locating tweets, clicking specific buttons on the page).

- `Mistral_Client`: Encapsulates the logic for communicating with the AI API.

- `UserSimulator`: Acts as the "Controller," utilizing the Browser and LLM classes to decide what to do next based on random probability checks.

## ⚠️ Disclaimer

This tool is for **educational purposes only**. Automating interactions on X (Twitter) _may_ violate their Terms of Service. Using this tool aggressively may result in account suspension <sub> although i didn't get banned while testing </sub>. The author is not responsible for any misuse of this software.

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.
