Проблема с NumPy
Переустановите NumPy и PyTorch:

pip uninstall numpy torch -y
pip install numpy torch --upgrade

Конфликт версий PyTorch и NumPy
Установите совместимые версии (например, для CPU):

pip install numpy==1.23.5 torch==2.0.1 --upgrade

Проблема с путями или кэшем
Очистите кэш pip и переустановите зависимости:

pip cache purge
pip install -r requirements.txt --force-reinstall