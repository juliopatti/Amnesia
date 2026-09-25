-- "Voltaria?" passa de sim/não para uma escala de 0 ("Nem a pau, Juvenal!") a
-- 5 ("Sem sombra de dúvidas"). NULL continua sendo "sem resposta".
-- Respostas antigas: sim vira 4 ("Voltaria, ué"); não vira 1 ("Não por livre
-- espontânea vontade"), os níveis equivalentes a um sim e a um não sem ênfase.
ALTER TABLE experiencias ADD COLUMN voltaria INTEGER CHECK (voltaria BETWEEN 0 AND 5);
UPDATE experiencias SET voltaria = CASE repetiria WHEN 1 THEN 4 WHEN 0 THEN 1 END;
ALTER TABLE experiencias DROP COLUMN repetiria;
