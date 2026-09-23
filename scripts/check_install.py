"""Import checks without model loading, browser access or a network listener."""
import importlib
import json
import shutil

def main():
    modules = ['streamlit', 'marker.converters.pdf', 'surya', 'torch',
               'torchvision', 'transformers', 'pymupdf', 'PIL', 'requests',
               'playwright.sync_api', 'cv2']
    for module in modules:
        importlib.import_module(module)
    import torch
    print(json.dumps({'imports': modules, 'cuda_available': torch.cuda.is_available(),
                      'ollama_on_path': bool(shutil.which('ollama')),
                      'nvidia_smi_on_path': bool(shutil.which('nvidia-smi'))}, indent=2))
    if not torch.cuda.is_available():
        print('WARNING: imports passed but CUDA is unavailable; GPU OCR is not ready.')
    if not shutil.which('ollama'):
        print('WARNING: install Ollama and obtain the selected model before Gemma review.')

if __name__ == '__main__':
    main()
