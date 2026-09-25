"""Casos de uso independentes de HTTP; armazenamento injetado nos testes."""

from dominio import horario_local


async def verificar_base(armazenamento, instante):
    categorias = await armazenamento.listar_categorias()
    contagens = await armazenamento.contar_registros()
    return {"estado": "ok", "verificado_em": horario_local(instante),
            "categorias": categorias, **contagens}
