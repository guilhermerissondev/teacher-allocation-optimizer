# Dados operacionais

Este diretório é o local padrão dos dados operacionais: uploads, banco SQLite,
jobs, cenários e resultados são gravados aqui, na mesma pasta de onde a
aplicação foi aberta. O caminho é identificado automaticamente a partir do
próprio pacote, então copiar a pasta da aplicação leva os dados junto.

Se esta pasta não aceitar escrita, a aplicação passa a usar
`%LOCALAPPDATA%\UniCesumar\AlocacaoDocente\v<versão>`. Em qualquer caso, o
diretório em uso aparece na linha `Dados operacionais:` durante a inicialização.

Para usar outro local, defina `ALOCACAO_DATA_DIR` ou execute:

```powershell
.\iniciar.ps1 --dados "D:\AlocacaoDocente"
```

Somente `README.md` e `.gitkeep` integram o pacote distribuído; o conteúdo
operacional fica fora do `MANIFESTO_RELEASE.json` e do ZIP da release.

Não compartilhe esse conteúdo sem aplicar as regras institucionais de retenção,
privacidade e descarte descritas na documentação de segurança.
