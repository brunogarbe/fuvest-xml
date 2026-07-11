def hide_text(text, shift_amount=5):
    """
    Hides text by shifting each character's ASCII value.

    Args:
        text (str): The input text to hide.
        shift_amount (int): The amount to shift each character (default is 5).

    Returns:
        str: The hidden text.
    """
    hidden_chars = []
    for char in text:
        hidden_chars.append(chr(ord(char) + shift_amount))
    return "".join(hidden_chars)

def unhide_text(hidden_text, shift_amount=5):
    """
    Unhides text by reversing the character ASCII value shift.

    Args:
        hidden_text (str): The hidden text to unhide.
        shift_amount (int): The amount used to shift each character during hiding (default is 5).

    Returns:
        str: The original unhidden text.
    """
    original_chars = []
    for char in hidden_text:
        original_chars.append(chr(ord(char) - shift_amount))
    return "".join(original_chars)

# Example usage:
original_message = "Library by Bruno Garbe Junior"
hidden_message = hide_text(original_message)
unhidden_message = unhide_text(hidden_message)

print(f"Original: {original_message}")
print(f"Hidden: {hidden_message}")
print(f"Unhidden: {unhidden_message}")