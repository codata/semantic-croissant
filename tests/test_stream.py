def process_text(text: str, state: dict) -> str:
    buffer = state["buffer"] + text
    in_think = state["in_think"]
    output = ""
    
    while True:
        if not in_think:
            idx = buffer.find("<think>")
            if idx != -1:
                output += buffer[:idx]
                output += "\n> 🧠 **Thinking:**\n> "
                in_think = True
                buffer = buffer[idx + 7:]
            else:
                partial_match = False
                for i in range(1, min(len(buffer), len("<think>")) + 1):
                    if "<think>".startswith(buffer[-i:]):
                        flush_len = len(buffer) - i
                        output += buffer[:flush_len]
                        buffer = buffer[flush_len:]
                        partial_match = True
                        break
                if not partial_match:
                    output += buffer
                    buffer = ""
                break
        else:
            idx = buffer.find("</think>")
            if idx != -1:
                think_content = buffer[:idx]
                output += think_content.replace("\n", "\n> ")
                output += "\n\n"
                in_think = False
                buffer = buffer[idx + 8:]
            else:
                partial_match = False
                for i in range(1, min(len(buffer), len("</think>")) + 1):
                    if "</think>".startswith(buffer[-i:]):
                        flush_len = len(buffer) - i
                        think_content = buffer[:flush_len]
                        output += think_content.replace("\n", "\n> ")
                        buffer = buffer[flush_len:]
                        partial_match = True
                        break
                if not partial_match:
                    output += buffer.replace("\n", "\n> ")
                    buffer = ""
                break

    state["buffer"] = buffer
    state["in_think"] = in_think
    return output

state = {"buffer": "", "in_think": False}
print(repr(process_text("Hello <thi", state)))
print(repr(process_text("nk>\nLet's think.\nWait.</t", state)))
print(repr(process_text("hink> The answer is 42.", state)))
