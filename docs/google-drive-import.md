# Importação de FASTQ do Google Drive

O menu **Gestão de Amostras → Importar do Google Drive** abre uma nova autorização
Google a cada uso. Após a autorização em uma aba do navegador, o usuário
seleciona arquivos no Google Picker exibido dentro do modal; um botão oferece
abertura em outra aba caso o WebView do navegador não o suporte. O worker do
BILBO transfere os pares R1/R2 diretamente para `/users/<id>/samples/<amostra>`.
O computador do usuário não recebe os arquivos.

## Para quem vai importar amostras

1. Abra **Gestão de Amostras → Importar do Google Drive**.
2. Clique em **Conectar ao Google Drive**, escolha sua conta Google e autorize
   o BILBO. A autorização é solicitada novamente sempre que o modal é aberto.
3. Selecione arquivos `FASTQ.gz` em pares R1/R2, confira os pares e clique em
   **Importar pares**. A transferência ocorre diretamente entre o Drive e o
   servidor do BILBO. Acompanhe o progresso no modal.

Você não precisa criar um projeto Google Cloud, instalar o Google Drive na sua
máquina nem baixar os arquivos antes. Se a conexão aparecer desabilitada, peça
ao administrador do BILBO para concluir a configuração única abaixo.

## Configuração única para quem mantém o BILBO

1. Crie **um único projeto Google Cloud para a instalação do BILBO** e habilite
   **Google Drive API** e **Google Picker API**. Cada usuário autoriza a própria
   conta no modal, sem configurar o Google Cloud.
2. Configure a tela de consentimento OAuth e um cliente do tipo **Aplicação Web**
   com o escopo `https://www.googleapis.com/auth/drive.file`.
3. Cadastre como origem JavaScript o endereço de acesso configurado no `.env`:
   `http://localhost:<BILBO_HOST_PORT>` para um túnel SSH, ou o valor HTTPS de
   `BILBO_PUBLIC_BASE_URL`. Cadastre a URI de retorno com
   `/drive/oauth/callback` ao final da mesma origem. Por exemplo, com a porta
   padrão: `http://localhost:8890/drive/oauth/callback`.
4. Crie uma chave de API para o Picker e anote o número do projeto (`appId`).
   Restrinja a chave às APIs necessárias e às origens utilizadas pelo Picker,
   incluindo `https://docs.google.com/*` conforme a documentação do Google.
5. Defina no `.env` do Compose, sem commitar os valores:

   ```text
   GOOGLE_DRIVE_CLIENT_ID=...
   GOOGLE_DRIVE_CLIENT_SECRET=...
   GOOGLE_DRIVE_API_KEY=...
   GOOGLE_DRIVE_APP_ID=...
   # Opcional se a origem vier de BILBO_HOST_PORT ou BILBO_PUBLIC_BASE_URL:
   GOOGLE_DRIVE_REDIRECT_URI=
   ```

O `SECRET_KEY` do BILBO deve estar definido e ser estável entre API e worker.
Ele é usado para cifrar as credenciais temporárias armazenadas no Redis. O
usuário autoriza novamente cada vez que abre o modal. Uma credencial de tarefa
permanece por até 72 horas para que downloads em andamento possam terminar.
Não inclua segredos OAuth, a chave de API nem o `.env` no Git. Para ativar uma
configuração nova numa instalação existente, execute `python3 init.py --no-build`;
os modelos e volumes de dados não precisam ser reinstalados.

## Regras de importação

- Somente pares completos de `.fastq.gz` ou `.fq.gz` são aceitos.
- `A01-F_S2_R1_001.fastq.gz` e `A01-F_S2_R2_001.fastq.gz` são salvos como
  `A01-F_S2_1.fastq.gz` e `A01-F_S2_2.fastq.gz`.
- O nome original, ID e tamanho do Drive ficam no registro da tarefa; a amostra
  só entra em `sample_stages` após os dois downloads passarem na verificação de
  tamanho e MD5 do Drive.
- Arquivos parciais terminam em `.part` e podem ser retomados por intervalo de
  bytes. O limite de espaço é checado antes do download de cada par.
- O Google Picker faz a seleção na conta que o usuário escolher. O modal do
  BILBO e a página auxiliar têm textos em português, inglês e espanhol.

Na tela de consentimento em modo **Testing**, tokens de atualização para escopos
Drive podem expirar em sete dias. Isso não impede o teste de uma biblioteca,
mas o projeto deve ser configurado para uso regular antes de importações longas.
