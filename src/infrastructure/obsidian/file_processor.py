import io
import logging
from pypdf import PdfReader

# Algunos PDFs válidos pero mal indexados disparan warnings muy ruidosos en consola.
# Seguimos extrayendo texto, pero ocultamos esos mensajes de bajo valor para la UI.
logging.getLogger("pypdf").setLevel(logging.ERROR)
logging.getLogger("pypdf._reader").setLevel(logging.ERROR)

def extract_text_from_file(uploaded_file) -> str:
    """
    Extrae el contenido de texto de un archivo subido de Streamlit (.pdf, .md, .txt).
    """
    if uploaded_file is None:
        return ""
    
    filename = uploaded_file.name.lower()
    content = ""

    try:
        file_bytes = uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else uploaded_file.read()

        if filename.endswith(".pdf"):
            reader = PdfReader(io.BytesIO(file_bytes))
            text = []
            for page in reader.pages:
                text.append(page.extract_text() or "")
            content = "\n".join(text)
        elif filename.endswith((".txt", ".md")):
            content = file_bytes.decode("utf-8", errors="replace")
        else:
            content = "[Unsupported file]"
    except Exception as e:
        content = f"[Error reading file: {str(e)}]"
    
    return content

def get_model_capabilities(model_name: str) -> dict:
    """
    Retorna capacidades del modelo actual.
    """
    m = model_name.lower()
    
    # Basado en la lista observada en model_list.txt
    is_gemini = "gemini" in m
    is_gemma = "gemma" in m
    is_lite = "lite" in m
    
    can_read_files = is_gemini # Por ahora asumimos que todos los Gemini configurados pueden
    context_size = "Large" if ("pro" in m or not is_lite) else "Intermediate"
    
    if is_gemma:
        can_read_files = False
        context_size = "Small"

    return {
        "can_read_files": can_read_files,
        "context_size": context_size,
        "warning": "This model does not support file attachments. Switch to Gemini." if not can_read_files else None
    }
