-- Onde o arquivo da foto está guardado: a chave no R2 local ou o id do arquivo no
-- Google Drive, conforme o armazenamento em uso. chave_r2 continua como chave do
-- envio, para que repetir o mesmo upload não duplique a foto.
ALTER TABLE fotos ADD COLUMN arquivo TEXT;
UPDATE fotos SET arquivo = chave_r2;
