INSTRUÇÕES RÁPIDAS - Indexador PDF (Windows)

1) Pré-requisitos:
   - Python 3.10+ instalado e "Add to PATH" marcado.
   - MySQL rodando localmente (você já tem o Workbench).
   - Certifique-se de que o usuário root e senha no config.py estão corretos.
   - Crie a pasta de export: C:\indexador\exports (ou ajuste EXPORT_FOLDER no config.py)
   - A pasta de PDFs (PDF_FOLDER) deve ser acessível pelo servidor.

2) Passos:
   a) Abra PowerShell/CMD, vá para a pasta do projeto:
      cd C:\caminho\para\indexador

   b) (Opcional) criar e ativar virtualenv:
      python -m venv venv
      venv\Scripts\activate

   c) Instalar dependências:
      pip install -r requirements.txt

   d) Inicializar banco e criar admin:
      python init_db.py
      (vai criar database indexador_db e usuário admin: victor.nomoto / joao1254)

   e) Rodar o sistema:
      python app.py

   f) Acesse:
      http://localhost:5000
      Usuário admin: victor.nomoto
      Senha: joao1254

3) Observações:
   - O export TXT é gerado com separador ';' e a última coluna é o nome do PDF.
   - Para visualizar o PDF no navegador, é preciso que o caminho de rede seja acessível pelo Windows e pelo browser. Caso prefira, abra o PDF no explorer.
   - Se tiver problemas de conexão MySQL, verifique se o MySQL está aceitando conexões locais e se usuário/senha batem.

4) Para compactar em .zip (Windows PowerShell):
   Compress-Archive -Path .\indexador\* -DestinationPath .\indexador.zip
