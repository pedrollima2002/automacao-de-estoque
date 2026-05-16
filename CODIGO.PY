import pyautogui
import time


pyautogui.PAUSE = 1         # Adiciona uma pausa de 1 segundo entre as ações
link = "https://dlp.hashtagtreinamentos.com/python/intensivao/login" # Define o link a ser aberto

pyautogui.press("win")      # Pressiona a tecla "Win" (tecla do Windows)
pyautogui.write("chrome")   # Escreve "chrome" para abrir o navegador Google Chrome
pyautogui.press("enter")    # Pressiona a tecla "Enter" para abrir o Chrome

pyautogui.write(link)     # Escreve o link na barra de endereços do navegador
pyautogui.press("enter")    # Pressiona a tecla "Enter" para acessar o link
time.sleep(3)              # Aguarda 3 segundos para a página carregar

pyautogui.click(x=918, y=503)  # Clica na posição (918, 503) para focar no campo de login
pyautogui.write("SEU_EMAIL")  # Escreve o email de login
pyautogui.press("tab")      # Pressiona a tecla "Tab" para ir para o campo de senha
pyautogui.write("SUA_SENHA")  # Escreve a senha
pyautogui.press("tab")      # Pressiona a tecla "Tab" para ir para o botão de login
pyautogui.press("enter")    # Pressiona a tecla "Enter" para fazer login

#pausa para carregar pagina
time.sleep(3)


#PASSO 3: ABRIR A BASE DE DADOS (importas o seu arquivo)
import pandas

tabela = pandas.read_csv("produtos.csv")
print(tabela)

for linha in tabela.index:
    
    #PASSO 4: CADASTRAR OS PRODUTOS
    pyautogui.click(x=932, y=360) #clicar no campo do codigo do produto
    
    #codigo
    codigo = tabela.loc[linha, "codigo"]
    pyautogui.write(codigo) #escrever o codigo do produto
    pyautogui.press("tab") #pressionar a tecla tab para ir para o campo do nome do produto
    
    #marca
    marca= tabela.loc[linha, "marca"]
    pyautogui.write(marca)
    pyautogui.press("tab") 
    
    #tipo
    tipo = tabela.loc[linha, "tipo"]
    pyautogui.write(tipo)
    pyautogui.press("tab") 
    
    #categoria
    categoria = tabela.loc[linha, "categoria"]
    pyautogui.write(str(categoria))
    pyautogui.press("tab") 
    
    
    #preco unitario
    preco_unitario = tabela.loc[linha, "preco_unitario"]
    pyautogui.write(str(preco_unitario))
    pyautogui.press("tab") 
   
    #custo
    custo = tabela.loc[linha, "custo"]
    pyautogui.write(str(custo))
    pyautogui.press("tab") 

    #obs
    
    obs = str(tabela.loc[linha, "obs"])
    if obs != "nan": #verificar se a célula de obs não está vazia
        pyautogui.write(obs)
    pyautogui.press("tab") 

    pyautogui.press("enter") #pressionar a tecla enter para cadastrar o produto 
    #voltar para o inicio da pagina
    pyautogui.scroll(5000)