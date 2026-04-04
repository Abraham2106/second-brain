import difflib
import re

def apply_unified_patch(original_content: str, patch_text: str) -> str:
    """
    Aplica un parche en formato unified diff al contenido original de forma robusta.
    """
    lines = original_content.splitlines(keepends=True)
    patch_lines = patch_text.splitlines(keepends=True)
    
    result = []
    i = 0 # line index in original
    p = 0 # line index in patch
    
    while p < len(patch_lines):
        line = patch_lines[p]
        
        # Saltarse encabezados
        if line.startswith("---") or line.startswith("+++") or line.strip() == "":
            p += 1
            continue
            
        # Hunk header: @@ -start,len +start,len @@
        match = re.search(r"@@ -(\d+),?\d* \+(\d+),?\d* @@", line)
        if match:
            start_line_orig = int(match.group(1)) - 1
            
            # 1. Añadir las líneas previas al hunk
            if i < start_line_orig:
                result.extend(lines[i:start_line_orig])
                i = start_line_orig
            
            p += 1
            # 2. Aplicar el hunk
            while p < len(patch_lines) and not patch_lines[p].startswith("@@"):
                pline = patch_lines[p]
                if pline.startswith(" "):
                    # Línea de contexto: validar que coincida
                    expected = pline[1:]
                    if i < len(lines) and lines[i] == expected:
                        result.append(lines[i])
                        i += 1
                    else:
                        found = lines[i] if i < len(lines) else "EOF"
                        raise ValueError(f"Conflict: Context mismatch at line {i+1}. Expected '{expected.strip()}', found '{found.strip()}'")
                elif pline.startswith("-"):
                    # Eliminación: validar que la línea exista
                    expected = pline[1:]
                    if i < len(lines) and lines[i] == expected:
                        i += 1 # Omitir de la salida
                    else:
                        found = lines[i] if i < len(lines) else "EOF"
                        raise ValueError(f"Conflict: Removal mismatch at line {i+1}. Expected '{expected.strip()}', found '{found.strip()}'")
                elif pline.startswith("+"):
                    # Adición: simplemente añadir al resultado
                    result.append(pline[1:])
                p += 1
        else:
            p += 1
            
    # 3. Añadir el resto de las líneas finales
    if i < len(lines):
        result.extend(lines[i:])
        
    return "".join(result)

def simple_append_patch(original_content: str, new_content: str) -> str:
    """Fallback si el agente solo quiere agregar al final."""
    return original_content.strip() + "\n\n" + new_content.strip() + "\n"
