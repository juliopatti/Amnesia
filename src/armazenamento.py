"""Adaptador D1. O domínio não depende dos objetos JavaScript deste binding."""

import json

from dominio import MAX_FOTOS


class ArmazenamentoD1:
    def __init__(self, banco):
        self.banco = banco

    def comando(self, sql, parametros=()):
        comando = self.banco.prepare(sql)
        return comando.bind(*parametros) if parametros else comando

    async def consultar(self, sql, parametros=()):
        comando = self.comando(sql, parametros)
        resultado = await comando.all()
        # A SDK atual já converte o resultado do binding em dict/list.
        return [dict(linha) for linha in resultado["results"]]

    async def listar_categorias(self):
        return await self.consultar("SELECT slug, nome FROM categorias ORDER BY nome")

    async def contar_registros(self):
        linhas = await self.consultar("""
            SELECT (SELECT count(*) FROM itens) AS itens,
                   (SELECT count(*) FROM experiencias) AS experiencias,
                   (SELECT count(*) FROM busca_itens) AS documentos_busca
        """)
        return linhas[0]

    async def listar_itens(self, categoria="", pagina=1):
        return await self.consultar("""
            SELECT id, nome, categoria, descricao FROM itens
            WHERE (? = '' OR categoria = ?) ORDER BY id DESC LIMIT 21 OFFSET ?
        """, (categoria, categoria, (pagina - 1) * 20))

    async def obter_item(self, item_id):
        linhas = await self.consultar("SELECT * FROM itens WHERE id = ?", (item_id,))
        return linhas[0] if linhas else None

    async def obter_experiencia(self, experiencia_id):
        linhas = await self.consultar("""
            SELECT e.*, i.nome, i.categoria FROM experiencias e
            JOIN itens i ON i.id = e.item_id WHERE e.id = ?
        """, (experiencia_id,))
        return linhas[0] if linhas else None

    def _inserir_item(self, item, chave, criado_em):
        return self.comando("""
            INSERT INTO itens (nome, categoria, descricao, detalhes, criado_em, chave_criacao)
            VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(chave_criacao) DO NOTHING
        """, (item["nome"], item["categoria"], item["descricao"],
              json.dumps(item["detalhes"], ensure_ascii=False), criado_em, chave))

    def _indexar(self, consulta_id, parametros):
        # Só fragmentos SQL internos entram em consulta_id; dados usam parâmetros.
        return [
            self.comando(f"DELETE FROM busca_itens WHERE rowid = ({consulta_id})", parametros),
            self.comando(f"""
                INSERT INTO busca_itens (rowid, nome, descricao, localizacao, detalhes, relatos, pedidos, tags)
                SELECT i.id, i.nome, i.descricao,
                    coalesce(json_extract(i.detalhes, '$.endereco'), '') || ' ' ||
                    coalesce(json_extract(i.detalhes, '$.bairro'), '') || ' ' ||
                    coalesce(json_extract(i.detalhes, '$.cidade'), ''),
                    coalesce((SELECT group_concat(value, ' ') FROM json_each(i.detalhes)), ''),
                    coalesce((SELECT group_concat(texto, ' ') FROM experiencias WHERE item_id = i.id), ''),
                    coalesce((SELECT group_concat(pedido, ' ') FROM experiencias WHERE item_id = i.id), ''),
                    coalesce((SELECT group_concat(t.tag, ' ') FROM tags_experiencia t
                              JOIN experiencias e ON e.id = t.experiencia_id WHERE e.item_id = i.id), '')
                FROM itens i WHERE i.id = ({consulta_id})
            """, parametros),
        ]

    async def salvar_item(self, item, chave, criado_em):
        consulta = "SELECT id FROM itens WHERE chave_criacao = ?"
        resultados = await self.banco.batch([
            self._inserir_item(item, chave, criado_em),
            *self._indexar(consulta, (chave,)), self.comando(consulta, (chave,)),
        ])
        return resultados[-1]["results"][0]["id"]

    async def salvar_experiencia(self, item, experiencia, chave, criado_em):
        comandos = []
        if item is not None:
            comandos.append(self._inserir_item(item, chave, criado_em))
            consulta_item, parametros_item = "SELECT id FROM itens WHERE chave_criacao = ?", (chave,)
        else:
            consulta_item, parametros_item = "SELECT id FROM itens WHERE id = ?", (experiencia["item_id"],)
        comandos.append(self.comando(f"""
            INSERT INTO experiencias
                (item_id, data, nota, texto, pedido, preco_centavos, repetiria, criado_em, chave_envio)
            VALUES (({consulta_item}), ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chave_envio) DO NOTHING
        """, (*parametros_item, experiencia["data"], experiencia["nota"], experiencia["texto"],
              experiencia["pedido"], experiencia["preco_centavos"], experiencia["repetiria"], criado_em, chave)))
        # changes() refere-se ao INSERT anterior: um reenvio não altera as tags originais.
        comandos.append(self.comando("""
            INSERT INTO tags_experiencia (experiencia_id, tag)
            SELECT e.id, t.value FROM experiencias e, json_each(?) t
            WHERE e.chave_envio = ? AND changes() > 0
        """, (json.dumps(experiencia["tags"], ensure_ascii=False), chave)))
        consulta = "SELECT item_id FROM experiencias WHERE chave_envio = ?"
        comandos.extend(self._indexar(consulta, (chave,)))
        comandos.append(self.comando("SELECT id, item_id FROM experiencias WHERE chave_envio = ?", (chave,)))
        resultados = await self.banco.batch(comandos)
        return dict(resultados[-1]["results"][0])

    async def listar_fotos(self, experiencia_id):
        return await self.consultar("SELECT * FROM fotos WHERE experiencia_id = ? ORDER BY ordem, id",
                                    (experiencia_id,))

    async def obter_foto(self, foto_id):
        linhas = await self.consultar("SELECT * FROM fotos WHERE id = ?", (foto_id,))
        return linhas[0] if linhas else None

    async def foto_por_chave(self, chave):
        linhas = await self.consultar("SELECT * FROM fotos WHERE chave_r2 = ?", (chave,))
        return linhas[0] if linhas else None

    async def salvar_foto(self, experiencia_id, chave, tamanho):
        resultados = await self.banco.batch([
            self.comando("""
                INSERT INTO fotos (experiencia_id, chave_r2, tipo_mime, tamanho_bytes, ordem)
                SELECT ?, ?, 'image/jpeg', ?, count(*) FROM fotos
                WHERE experiencia_id = ? HAVING count(*) < ?
                ON CONFLICT(chave_r2) DO NOTHING
            """, (experiencia_id, chave, tamanho, experiencia_id, MAX_FOTOS)),
            self.comando("SELECT * FROM fotos WHERE chave_r2 = ?", (chave,)),
        ])
        linhas = resultados[-1]["results"]
        if not linhas:
            raise ValueError(f"Cada experiência aceita até {MAX_FOTOS} fotos.")
        return dict(linhas[0])


class ArmazenamentoR2:
    def __init__(self, bucket):
        self.bucket = bucket

    async def salvar(self, chave, conteudo):
        await self.bucket.put(chave, conteudo, {"httpMetadata": {"contentType": "image/jpeg"}})

    async def excluir(self, chave):
        await self.bucket.delete(chave)

    async def obter(self, chave):
        return await self.bucket.get(chave)
