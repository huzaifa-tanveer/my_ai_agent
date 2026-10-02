import os
import json
from datetime import datetime

import pandas as pd
from openai import OpenAI
from ddgs import DDGS
from pypdf import PdfReader


# =========================================================
# OpenRouter Client
# =========================================================

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)


# =========================================================
# Persistent Memory
# =========================================================

MEMORY_FILE = "memory.json"


def load_memory():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as file:
                return json.load(file)
        except Exception:
            return {}

    return {}


def save_memory(memory_data):
    with open(MEMORY_FILE, "w", encoding="utf-8") as file:
        json.dump(
            memory_data,
            file,
            ensure_ascii=False,
            indent=4
        )


memory = load_memory()


# =========================================================
# Python Tools
# =========================================================

def add_numbers(a, b):
    return a + b


def get_current_datetime():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def web_search(query):
    try:
        results = DDGS().text(
            query,
            max_results=5
        )

        formatted_results = []

        for result in results:
            formatted_results.append({
                "title": result.get("title"),
                "url": result.get("href"),
                "snippet": result.get("body")
            })

        return formatted_results

    except Exception as e:
        return f"Web search error: {e}"


def save_user_memory(key, value):
    memory[key] = value
    save_memory(memory)

    return f"Saved {key}: {value}"


def get_user_memory(key):
    if key in memory:
        return memory[key]

    return "No saved information found."


# =========================================================
# TXT Reader
# =========================================================

def read_text_file(file_path):

    if not os.path.exists(file_path):
        return f"File not found: {file_path}"

    if not file_path.lower().endswith(".txt"):
        return "This tool only reads TXT files."

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()

        if len(content) > 15000:
            content = content[:15000]
            content += (
                "\n\n[File was large. "
                "Only the first 15,000 characters were loaded.]"
            )

        return content

    except Exception as e:
        return f"Error reading TXT file: {e}"


# =========================================================
# CSV Reader
# =========================================================

def read_csv_file(file_path):

    if not os.path.exists(file_path):
        return f"File not found: {file_path}"

    if not file_path.lower().endswith(".csv"):
        return "This tool only reads CSV files."

    try:
        df = pd.read_csv(file_path)

        info = {
            "rows": len(df),
            "columns": df.columns.tolist(),
            "preview": df.head(10).to_dict(orient="records")
        }

        return info

    except Exception as e:
        return f"Error reading CSV file: {e}"


# =========================================================
# PDF Reader
# =========================================================

def read_pdf_file(file_path):

    if not os.path.exists(file_path):
        return f"File not found: {file_path}"

    if not file_path.lower().endswith(".pdf"):
        return "This tool only reads PDF files."

    try:
        reader = PdfReader(file_path)

        text = ""

        for page_number, page in enumerate(reader.pages, start=1):

            page_text = page.extract_text()

            if page_text:
                text += f"\n--- Page {page_number} ---\n"
                text += page_text

        if not text.strip():
            return (
                "No readable text was found in this PDF. "
                "It may be a scanned/image PDF."
            )

        if len(text) > 20000:
            text = text[:20000]

            text += (
                "\n\n[PDF was large. "
                "Only the first 20,000 characters were loaded.]"
            )

        return {
            "pages": len(reader.pages),
            "content": text
        }

    except Exception as e:
        return f"Error reading PDF: {e}"


# =========================================================
# Tool Definitions
# =========================================================

tools = [

    # -------------------------
    # Calculator
    # -------------------------

    {
        "type": "function",
        "function": {
            "name": "add_numbers",
            "description": "Add two numbers together.",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {
                        "type": "number"
                    },
                    "b": {
                        "type": "number"
                    }
                },
                "required": ["a", "b"]
            }
        }
    },

    # -------------------------
    # Date / Time
    # -------------------------

    {
        "type": "function",
        "function": {
            "name": "get_current_datetime",
            "description": "Get the current local date and time.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },

    # -------------------------
    # Web Search
    # -------------------------

    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for current, recent, latest "
                "or live information."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    }
                },
                "required": ["query"]
            }
        }
    },

    # -------------------------
    # Save Persistent Memory
    # -------------------------

    {
        "type": "function",
        "function": {
            "name": "save_user_memory",
            "description": (
                "Save information when the user explicitly "
                "asks the agent to remember something."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string"
                    },
                    "value": {
                        "type": "string"
                    }
                },
                "required": ["key", "value"]
            }
        }
    },

    # -------------------------
    # Get Persistent Memory
    # -------------------------

    {
        "type": "function",
        "function": {
            "name": "get_user_memory",
            "description": (
                "Retrieve previously saved information "
                "about the user."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string"
                    }
                },
                "required": ["key"]
            }
        }
    },

    # -------------------------
    # TXT Reader
    # -------------------------

    {
        "type": "function",
        "function": {
            "name": "read_text_file",
            "description": (
                "Read and summarize a TXT file "
                "from the computer."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the TXT file"
                    }
                },
                "required": ["file_path"]
            }
        }
    },

    # -------------------------
    # CSV Reader
    # -------------------------

    {
        "type": "function",
        "function": {
            "name": "read_csv_file",
            "description": (
                "Read a CSV file and inspect its rows, "
                "columns and sample records."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the CSV file"
                    }
                },
                "required": ["file_path"]
            }
        }
    },

    # -------------------------
    # PDF Reader
    # -------------------------

    {
        "type": "function",
        "function": {
            "name": "read_pdf_file",
            "description": (
                "Read and summarize text from a PDF file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the PDF file"
                    }
                },
                "required": ["file_path"]
            }
        }
    }

]


# =========================================================
# Conversation Memory
# =========================================================

messages = [
    {
        "role": "system",
        "content": """
You are a helpful AI agent.

You have access to several tools.

Rules:

1. Use add_numbers for arithmetic.

2. Use get_current_datetime when the user asks
   for the current date or time.

3. Use web_search for latest, current, recent,
   live, or internet-based information.

4. Use save_user_memory only when the user
   explicitly asks you to remember or save something.

5. Use get_user_memory when the user asks about
   previously saved information.

6. Use read_text_file when the user asks you
   to read, inspect, explain, or summarize a TXT file.

7. Use read_csv_file when the user asks you
   to inspect or summarize a CSV file.

8. Use read_pdf_file when the user asks you
   to read, inspect, explain, or summarize a PDF.

9. Never claim that a file was successfully read
   unless the file tool actually succeeded.

10. Never claim something was saved to long-term
    memory unless save_user_memory was actually used.

11. After web searches or file reading,
    explain the result clearly.

12. Keep answers simple, natural and helpful.
"""
    }
]


# =========================================================
# Start Agent
# =========================================================

print("AI Agent started. Type 'exit' to stop.\n")


# =========================================================
# Main Agent Loop
# =========================================================

while True:

    user_input = input("You: ")

    if user_input.lower().strip() == "exit":
        print("Agent: Goodbye!")
        break

    messages.append({
        "role": "user",
        "content": user_input
    })

    try:

        # -------------------------------------------------
        # First AI Request
        # -------------------------------------------------

        response = client.chat.completions.create(
            model="openrouter/free",
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )

        message = response.choices[0].message


        # -------------------------------------------------
        # Tool Calling
        # -------------------------------------------------

        if message.tool_calls:

            messages.append(message)

            for tool_call in message.tool_calls:

                function_name = tool_call.function.name

                arguments = json.loads(
                    tool_call.function.arguments
                )

                print(
                    f"[Tool called: {function_name} "
                    f"| Arguments: {arguments}]"
                )

                result = None


                # -----------------------------------------
                # Calculator
                # -----------------------------------------

                if function_name == "add_numbers":

                    result = add_numbers(
                        arguments["a"],
                        arguments["b"]
                    )


                # -----------------------------------------
                # Date / Time
                # -----------------------------------------

                elif function_name == "get_current_datetime":

                    result = get_current_datetime()


                # -----------------------------------------
                # Web Search
                # -----------------------------------------

                elif function_name == "web_search":

                    result = web_search(
                        arguments["query"]
                    )


                # -----------------------------------------
                # Save Memory
                # -----------------------------------------

                elif function_name == "save_user_memory":

                    result = save_user_memory(
                        arguments["key"],
                        arguments["value"]
                    )


                # -----------------------------------------
                # Get Memory
                # -----------------------------------------

                elif function_name == "get_user_memory":

                    result = get_user_memory(
                        arguments["key"]
                    )


                # -----------------------------------------
                # TXT
                # -----------------------------------------

                elif function_name == "read_text_file":

                    result = read_text_file(
                        arguments["file_path"]
                    )


                # -----------------------------------------
                # CSV
                # -----------------------------------------

                elif function_name == "read_csv_file":

                    result = read_csv_file(
                        arguments["file_path"]
                    )


                # -----------------------------------------
                # PDF
                # -----------------------------------------

                elif function_name == "read_pdf_file":

                    result = read_pdf_file(
                        arguments["file_path"]
                    )


                # -----------------------------------------
                # Unknown Tool
                # -----------------------------------------

                else:

                    result = (
                        f"Unknown tool requested: "
                        f"{function_name}"
                    )


                # -----------------------------------------
                # Send Tool Result Back
                # -----------------------------------------

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(
                        result,
                        ensure_ascii=False,
                        default=str
                    )
                })


            # -------------------------------------------------
            # Final AI Response after Tool Result
            # -------------------------------------------------

            final_response = client.chat.completions.create(
                model="openrouter/free",
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )

            answer = final_response.choices[0].message.content


        else:

            answer = message.content


        # -------------------------------------------------
        # Print Result
        # -------------------------------------------------

        if answer:
            print("\nAgent:", answer)
        else:
            print("\nAgent: No text response received.")

        print()


        # -------------------------------------------------
        # Short-term Conversation Memory
        # -------------------------------------------------

        messages.append({
            "role": "assistant",
            "content": answer or ""
        })


    except Exception as e:

        print("\nError:", e)
        print()