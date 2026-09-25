"""HTML da base local. Formulários entram no próximo incremento."""

from html import escape


def pagina_inicial(categorias):
    nomes = " · ".join(escape(categoria["nome"]) for categoria in categorias)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>amnesia — registro de experiências</title>
  <style>
    :root {{ color-scheme: light; font-family: system-ui, sans-serif; color: #292821;
      background: #f5f3ec; }}
    body {{ margin: 0; padding: 24px; }}
    main {{ max-width: 560px; margin: 12vh auto; }}
    h1 {{ font-size: clamp(3rem, 12vw, 5rem); letter-spacing: -.07em; margin: 0; }}
    p {{ line-height: 1.6; }}
    .categorias {{ color: #46624c; font-weight: 650; }}
    .cartao {{ margin-top: 32px; padding: 24px; background: #fffdf8;
      border: 1px solid #dad8cf; border-radius: 18px; }}
  </style>
</head>
<body><main>
  <h1>amnesia<span aria-hidden="true">.</span></h1>
  <p>Você já esteve aqui. Óbvio que não lembra.</p>
  <p class="categorias">{nomes}</p>
  <div class="cartao">
    <strong>Um lugar para guardar o que a cabeça não guardou.</strong>
    <p>Seu caderno está tomando forma. O registro de experiências chega na próxima etapa.</p>
  </div>
</main></body></html>"""
