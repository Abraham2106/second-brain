from typing import Optional

class BaseCallback:
    """Clase base para manejar eventos del Orquestador en tiempo real."""
    
    def on_agent_start(self, agent_name: str, instruction: str):
        """Se llama cuando un agente comienza su ejecución."""
        pass
        
    def on_agent_end(self, agent_name: str, result: str):
        """Se llama cuando un agente termina su ejecución."""
        pass
        
    def on_system_message(self, message: str, mtype: str = "info"):
        """Se llama para mensajes del sistema (guardado de archivos, parches, etc)."""
        pass

    def on_builder_action(self, action_type: str, filepath: str, result: str):
        """Específico para acciones del Builder (vault_file, patch, etc)."""
        pass
