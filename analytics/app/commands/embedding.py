class GenerateEmbeddingCommand:
    @staticmethod
    def generate(text, model=None):
        """Generate a semantic embedding for the given text."""
        if not text:
            return None
            
        if model is None:
            # In a real scenario, we would load a default model here
            # For this command, we expect the model to be provided or mocked
            return [0.0] * 1536
            
        # Call the model's encode method
        vector = model.encode(text)
        return vector
