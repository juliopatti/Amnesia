"""Casos de uso independentes de HTTP; armazenamento injetado nos testes."""

from dominio import (horario_local, preparar_busca, preparar_item, preparar_experiencia,
                     validar_chave, validar_foto)


async def verificar_base(armazenamento, instante):
    categorias = await armazenamento.listar_categorias()
    contagens = await armazenamento.contar_registros()
    return {"estado": "ok", "verificado_em": horario_local(instante),
            "categorias": categorias, **contagens}


async def buscar(armazenamento, criterios, pagina=1, por_pagina=20):
    """Sem palavras pesquisáveis (só símbolos), não lista tudo como se a busca estivesse vazia."""
    busca = preparar_busca(**criterios)
    if busca["texto"] and not busca["expressao"]:
        return {"busca": busca, "itens": [], "tem_mais": False}
    itens = await armazenamento.buscar_itens(busca, pagina, por_pagina)
    return {"busca": busca, "itens": itens[:por_pagina], "tem_mais": len(itens) > por_pagina}


async def criar_item(armazenamento, dados, chave, instante):
    validar_chave(chave)
    item = preparar_item(**dados)
    return await armazenamento.salvar_item(item, chave, horario_local(instante))


async def registrar_experiencia(armazenamento, dados, chave, instante, *, item_id=None, novo_item=None):
    validar_chave(chave)
    if (item_id is None) == (novo_item is None):
        raise ValueError("Escolha um item existente ou informe um novo item.")
    criado_em = horario_local(instante)
    item = preparar_item(**novo_item) if novo_item is not None else None
    experiencia = preparar_experiencia(item_id, hoje=criado_em[:10], **dados)
    if item_id is not None and not await armazenamento.obter_item(item_id):
        raise LookupError("Esse item não foi encontrado.")
    return await armazenamento.salvar_experiencia(item, experiencia, chave, criado_em)


async def anexar_foto(armazenamento, arquivos, experiencia_id, chave, conteudo, tipo):
    validar_chave(chave)
    validar_foto(conteudo, tipo)
    if not await armazenamento.obter_experiencia(experiencia_id):
        raise LookupError("Essa experiência não foi encontrada.")
    chave_r2 = f"experiencias/{experiencia_id}/{chave}.jpg"
    existente = await armazenamento.foto_por_chave(chave_r2)
    if existente:
        return existente
    await arquivos.salvar(chave_r2, conteudo)
    try:
        return await armazenamento.salvar_foto(experiencia_id, chave_r2, len(conteudo))
    except Exception:
        # Uma resposta perdida ou envio concorrente pode já ter confirmado a foto.
        existente = await armazenamento.foto_por_chave(chave_r2)
        if existente:
            return existente
        await arquivos.excluir(chave_r2)
        raise


async def editar_item(armazenamento, item_id, dados):
    item = preparar_item(**dados)
    if not await armazenamento.obter_item(item_id):
        raise LookupError("Esse item não foi encontrado.")
    await armazenamento.atualizar_item(item_id, item)


async def editar_experiencia(armazenamento, experiencia_id, dados, instante):
    atual = await armazenamento.obter_experiencia(experiencia_id)
    if not atual:
        raise LookupError("Essa experiência não foi encontrada.")
    # Data apagada no formulário mantém a original, em vez de virar "hoje" sem aviso.
    dados = {**dados, "data": dados.get("data") or atual["data"]}
    experiencia = preparar_experiencia(atual["item_id"], hoje=horario_local(instante)[:10], **dados)
    await armazenamento.atualizar_experiencia(experiencia_id, experiencia)
    return atual["item_id"]


async def _excluir_arquivos(arquivos, chaves):
    """R2 e D1 não têm transação conjunta: o banco já foi atualizado; falhas viram objetos órfãos."""
    orfaos = 0
    for chave in chaves:
        try:
            await arquivos.excluir(chave)
        except Exception:
            orfaos += 1
    return orfaos


async def excluir_experiencia(armazenamento, arquivos, experiencia_id):
    experiencia = await armazenamento.obter_experiencia(experiencia_id)
    if not experiencia:
        raise LookupError("Essa experiência não foi encontrada.")
    fotos = await armazenamento.listar_fotos(experiencia_id)
    await armazenamento.excluir_experiencia(experiencia_id, experiencia["item_id"])
    orfaos = await _excluir_arquivos(arquivos, [foto["chave_r2"] for foto in fotos])
    return {"item_id": experiencia["item_id"], "orfaos": orfaos}


async def excluir_foto(armazenamento, arquivos, foto_id):
    foto = await armazenamento.obter_foto(foto_id)
    if not foto:
        raise LookupError("Essa foto não foi encontrada.")
    await armazenamento.excluir_foto(foto_id)
    orfaos = await _excluir_arquivos(arquivos, [foto["chave_r2"]])
    return {"experiencia_id": foto["experiencia_id"], "orfaos": orfaos}
