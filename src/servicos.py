"""Casos de uso independentes de HTTP; armazenamento injetado nos testes."""

from dominio import horario_local, preparar_item, preparar_experiencia, validar_chave, validar_foto


async def verificar_base(armazenamento, instante):
    categorias = await armazenamento.listar_categorias()
    contagens = await armazenamento.contar_registros()
    return {"estado": "ok", "verificado_em": horario_local(instante),
            "categorias": categorias, **contagens}


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
