# Evonik Training — Protótipo local

Protótipo funcional de treinamento corporativo baseado na apresentação **Integração de Segurança_2026.pptx — REV08, Site Americana**.

## Requisitos
- Python 3.10+
- Windows, macOS ou Linux

## Instalação
```bash

# Windows PowerShell:
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
copy .env.example .env

# macOS/Linux:
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

## Executar
```bash
python app.py
```
Abra http://127.0.0.1:5000

O banco é criado automaticamente em `instance/database.db`.

## Acessos de demonstração
- RH: `admin@evonik.local` / `Evonik@2026!`
- Colaborador em andamento: `bruno.costa@evonik.local` / `Colab@2026!`
- Colaboradora concluída: `carla.souza@evonik.local` / `Colab@2026!`
- Convite pendente: `ana.martins@evonik.local`
  - Link local: `http://127.0.0.1:5000/ativar/demo-convite-ana-2026`

Os usuários e senhas são fictícios.

## Fluxo demonstrável
1. RH entra no painel.
2. RH cadastra colaborador e copia o link de convite.
3. Colaborador ativa a conta e define senha.
4. Colaborador estuda módulos em sequência.
5. A avaliação é corrigida no backend; o gabarito não é enviado à tela do colaborador.
6. Nota mínima configurável pelo RH (inicialmente 70%).
7. Aprovação libera o módulo seguinte.
8. Ao concluir todos os módulos, o certificado PDF é disponibilizado.
9. RH acompanha progresso, tentativas e notas.
