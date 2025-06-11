def clean_json_input(json_str: str) -> str:
    """
    Clean the JSON input by removing markdown code block markers and any extra whitespace.
    """
    # Remove markdown code block markers if present
    json_str = json_str.replace("```json", "").replace("```", "")
    # Remove any leading/trailing whitespace
    return json_str.strip()