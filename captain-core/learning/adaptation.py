"""Adapt responses based on learned preferences."""
from learning.preferences import infer_communication_style


async def adapt_response(response: str) -> str:
    """Adjust response length/style based on learned preferences."""
    style_info = await infer_communication_style()
    style = style_info.get("style", "balanced")

    if style == "concise" and len(response) > 800:
        # Truncate to key points for concise preference
        lines = response.split("\n")
        if len(lines) > 10:
            return "\n".join(lines[:10]) + "\n\n...(truncated for brevity)"

    return response
