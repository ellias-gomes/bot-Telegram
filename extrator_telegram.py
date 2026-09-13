import os
from dotenv import load_dotenv
from groq import Groq
import json
import time
from datetime import date, datetime
import telebot
from collections import deque

# Carrega as variáveis do arquivo .env (se existir)
load_dotenv()

# Chaves de API
CHAVE_API_TELEGRAM = os.getenv('CHAVE_API_TELEGRAM')
ID_APROVADO = os.getenv('ID_APROVADO').split(',')  # Lista de IDs permitidos
CHAVE_API_GROQ = os.getenv('CHAVE_API_GROQ')

# Verifica se a chave da API do Groq está definida
if not CHAVE_API_GROQ:
    raise ValueError("Chave da API não encontrada. Defina CHAVE_API_GROQ no .env ou exporte no terminal.")

# Cria o cliente com a chave
client = Groq(api_key = CHAVE_API_GROQ)

# Coletando payloads do sistema
system_prompt = open('payload/system_prompt.txt', 'r').read().replace('{data_ref}', date.today().strftime('%Y-%m-%d'))

# Substituindo o valor de tokens do arquivo de configuração
# Carregando o arquivo de configuração JSON
with open("metadata/ia_config.json", "r", encoding="utf-8") as file:
    ia_config = json.load(file)

# Substituindo o valor de tokens no system_prompt
system_prompt = system_prompt.replace('{tokens}', str(ia_config['tokens_lia']))

# Criando um dicionário dos comandos dentro do Telegram, unificando com base nas chaves em comum
comandos_unificados = {
    chave: {
        'comando': ia_config['comandos_telegram'][chave],
        'descricao': ia_config['comandos_descricao'][chave],
        'agente': ia_config['comandos_agentes'][chave]
    }
    for chave in ia_config['comandos_telegram'].keys()
}

# Substituindo o valor de comandos no system_prompt
system_prompt = system_prompt.replace('{comandos}', json.dumps(comandos_unificados, indent=4, ensure_ascii=False))

# Criando variável para armazenar o histórico de mensagens por usuário
historico_lia = {}

# Função que recebe uma pergunta e retorna a resposta
def perguntar_groq(pergunta, historico=None):
    # Se houver histórico, adiciona ao system_prompt
    if historico:
        historico_str = "\n".join(historico)
        system_prompt_with_history = system_prompt + f"\n\nHistórico de mensagens do usuário:\n{historico_str}"
    else:
        system_prompt_with_history = system_prompt
    completion = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
        {
            "role": "system",
            "content": system_prompt_with_history
        },
        {
            "role": "user",
            "content": pergunta
        }
        ],
        temperature=1,
        max_completion_tokens=ia_config['tokens_lia'],
        top_p=1,
        reasoning_effort="medium",
        stream=False,
        stop=None
    )

    return completion.choices[0].message.content

# Configurando Telegram
bot = telebot.TeleBot(CHAVE_API_TELEGRAM)
@bot.message_handler(func=lambda message: True)
def input_message(message):
    # Analisando tempo de resposta do bot
    start_time = datetime.now()

    # Verificação de segurança das contas permitidas
    if str(message.from_user.id) not in ID_APROVADO:
        bot.reply_to(message, '⛔ Acesso negado. Este é um bot privado.')
        print(f'⚠️ Tentativa de acesso bloqueada! ID: {message.from_user.id}')
        return

    user_input = message.text
    print(f'📩 Mensagem recebida: {user_input} | Data mensagem: {datetime.now().strftime("%Y-%m-%d")} | Enviada por: {message.from_user.id}')
    # bot.reply_to(message, '⏳ Processando sua solicitação...')

    # Mantendo o histórico de mensagens por usuário para contexto
    if message.from_user.id not in historico_lia:
        historico_lia[message.from_user.id] = deque(maxlen=ia_config['quantidade_mensagens_contexto'])  # Mantém as últimas N mensagens
    historico_lia[message.from_user.id].append(user_input)

    # Para debug:
    print(f'📝 Histórico atual do usuário {message.from_user.id}: {list(historico_lia[message.from_user.id])}')

    # Faz a pergunta para a Groq e obtém a resposta
    resposta = perguntar_groq(user_input, historico=list(historico_lia[message.from_user.id]))

    # Extrai o texto da resposta, caso venha com formatação:
    # "RESPOSTA_USUARIO": {
    #     "mensagem": "Coloque a sua resposta para o usuário aqui."
    # }
    try:
        resposta_json = json.loads(resposta)
        if "RESPOSTA_USUARIO" in resposta_json and "mensagem" in resposta_json["RESPOSTA_USUARIO"]:
            resposta = resposta_json["RESPOSTA_USUARIO"]["mensagem"]
    except json.JSONDecodeError:
        # Se não for JSON, mantém a resposta original
        pass

    # bot.reply_to(message, f'💬 Resposta da Lia:\n{resposta}')
    bot.reply_to(message, f'💬 {resposta}')

    # Salva as mensagens em um arquivo JSON, realizando o append com a data e hora
    log_entry = {
        "data": datetime.now().strftime("%Y-%m-%d:%H:%M:%S"),
        "usuario": message.from_user.id,
        "mensagem": user_input,
        "resposta": resposta
    }
    with open('out/log_mensagens.json', 'a') as log_file:
        log_file.write(json.dumps(log_entry) + '\n')

    # Calcula o tempo de resposta do bot
    end_time = datetime.now()
    tempo_resposta = (end_time - start_time).total_seconds()
    print(f'⏱️ Tempo de resposta do bot: {tempo_resposta:.2f} segundos')

    print('\n' + '-'*50 + '\n')

# # Lê a entrada do usuário (via terminal) - isso é útil para testes sem usar o Telegram
# if __name__ == "__main__":
#     entrada = input("Digite sua pergunta: ")
#     resposta = perguntar_groq(entrada)
#     print("\nResposta da Groq:")
#     print(resposta)

# Inicia o bot do Telegram
print('🤖 Servidor rodando com ChatGPT na Nuvem (Groq)')
print('🔗 Conectando ao Telegram...')
print('\n' + '-'*50 + '\n')
while True:
    try:
        # Reduzimos o timeout de 60 para 20. 
        # Isso força o bot a "piscar" a conexão com mais frequência,
        # sobrevivendo às trocas de Wi-Fi para 4G.
        bot.polling(none_stop=True, timeout=20, long_polling_timeout=20)
    except Exception as e:
        print(f"⚠️ Erro de conexão com o Telegram: {e}")
        print("🔄 Aguardando 5 segundos para reconectar...")
        time.sleep(5) # Reduzido para tentar voltar mais rápido