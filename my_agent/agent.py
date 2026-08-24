from strands import Agent, tool
from strands_tools import calculator, current_time


@tool
def letter_counter(word: str, letter: str) -> int:
    """
    Count occurrences of a specific letter in a word.
    """
    if not isinstance(word, str) or not isinstance(letter, str):
        return 0
    if len(letter) != 1:
        raise ValueError("The 'letter' parameter must be a single character")
    return word.lower().count(letter.lower())


agent = Agent(tools=[calculator, current_time, letter_counter])

message = """
Check three things for me:
1. What time is it right now?
2. What is 3111696 divided by 74088?
3. How many letter "r"s are in the word "strawberry"?
"""

agent(message)
