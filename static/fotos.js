/* Sem bibliotecas de imagem: o canvas reduz, reencoda em JPEG e remove metadados. */
(() => {
  const LIMITE = 768 * 1024;
  const selecoes = new WeakMap();

  function atualizarFormulario() {
    const opcao = document.querySelector('#categoria')?.selectedOptions[0];
    const nome = document.querySelector('#nome');
    const relato = document.querySelector('#texto');
    if (opcao && nome) nome.placeholder = opcao.dataset.exemplo;
    if (opcao && relato) relato.placeholder = opcao.dataset.relato;
    document.querySelectorAll('[data-categoria]').forEach(grupo => {
      const selecionada = document.querySelector('#categoria')?.value || 'lugar';
      grupo.hidden = grupo.dataset.categoria !== selecionada;
      grupo.querySelectorAll('input').forEach(input => { input.disabled = grupo.hidden; });
    });
    const nota = document.querySelector('input[name="nota"]:checked')?.value || '';
    document.querySelectorAll('[data-estrela]').forEach(estrela => {
      const inteira = Number(estrela.dataset.estrela);
      estrela.classList.toggle('cheia', Number(nota) >= inteira);
      estrela.classList.toggle('meia', Number(nota) === inteira - 0.5);
    });
    const saida = document.querySelector('.nota-atual');
    if (saida) {
      saida.hidden = false;
      saida.textContent = nota === '' ? 'Sem nota' : `${nota.replace('.', ',')} / 5`;
    }
  }

  function aviso(mensagem) {
    const caixa = document.querySelector('#erro-form') || document.querySelector('#resultado-upload');
    caixa.hidden = false;
    caixa.textContent = mensagem;
    caixa.scrollIntoView({block: 'nearest'});
  }

  async function reduzir(arquivo) {
    if (!arquivo.type.startsWith('image/') || arquivo.size > 20 * 1024 * 1024) {
      throw new Error('Escolha uma imagem de até 20 MB.');
    }
    let imagem;
    try { imagem = await createImageBitmap(arquivo); }
    catch { throw new Error('O navegador não conseguiu abrir esta foto. Tente JPEG, PNG ou WebP.'); }
    try {
      const canvas = document.createElement('canvas');
      let escala = Math.min(1, 1600 / Math.max(imagem.width, imagem.height));
      for (let tentativa = 0; tentativa < 5; tentativa++) {
        canvas.width = Math.max(1, Math.round(imagem.width * escala));
        canvas.height = Math.max(1, Math.round(imagem.height * escala));
        const contexto = canvas.getContext('2d');
        contexto.fillStyle = '#ffffff';
        contexto.fillRect(0, 0, canvas.width, canvas.height);
        contexto.drawImage(imagem, 0, 0, canvas.width, canvas.height);
        const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.82));
        if (blob && blob.size <= LIMITE) return blob;
        escala *= 0.75;
      }
      throw new Error('Não conseguimos diminuir esta foto o suficiente.');
    } finally { imagem.close(); }
  }

  function selecionarFotos(input) {
    const anteriores = selecoes.get(input) || [];
    anteriores.forEach(foto => { if (foto.previa) URL.revokeObjectURL(foto.previa); });
    const lista = document.querySelector('#previas');
    lista.replaceChildren();
    const total = Number(input.closest('form')?.dataset.total || 0);
    if (input.files.length > 3 - total) {
      input.value = '';
      selecoes.set(input, []);
      aviso(`Escolha até ${3 - total} foto(s).`);
      return;
    }
    const fotos = [...input.files].map(arquivo => {
      const foto = {arquivo, chave: crypto.randomUUID().replaceAll('-', ''), enviada: false};
      const linha = document.createElement('li');
      const rotulo = document.createElement('span');
      rotulo.textContent = `${arquivo.name} · preparando…`;
      linha.append(rotulo);
      lista.append(linha);
      foto.preparo = reduzir(arquivo).then(blob => {
        foto.blob = blob;
        foto.previa = URL.createObjectURL(blob);
        const img = document.createElement('img');
        img.src = foto.previa;
        img.alt = '';
        linha.prepend(img);
        rotulo.textContent = `${arquivo.name} · ${Math.ceil(blob.size / 1024)} KiB`;
      }).catch(erro => {
        foto.erro = erro.message;
        rotulo.textContent = `${arquivo.name} · ${erro.message} O texto pode ser salvo mesmo assim.`;
      });
      return foto;
    });
    selecoes.set(input, fotos);
  }

  async function resposta(response) {
    let dados;
    try { dados = await response.json(); }
    catch { throw new Error('A resposta não chegou completa. Tente novamente.'); }
    if (!response.ok) throw new Error(dados.erro || 'Não foi possível concluir. Tente novamente.');
    return dados;
  }

  async function enviarFotos(fotos, salvo) {
    const caixa = document.querySelector('#resultado-upload');
    caixa.hidden = false;
    caixa.textContent = 'Experiência guardada. Agora estamos enviando as fotos…';
    const falhas = [];
    for (const foto of fotos) {
      if (foto.enviada) continue;
      await foto.preparo;
      try {
        if (foto.erro) throw new Error(foto.erro);
        await resposta(await fetch(`/uploads/${salvo.experiencia_id}`, {
          method: 'POST', headers: {'Content-Type': 'image/jpeg', 'X-Chave-Foto': foto.chave},
          body: foto.blob, signal: AbortSignal.timeout(30000)
        }));
        foto.enviada = true;
      } catch (erro) { falhas.push(`${foto.arquivo.name}: ${erro.message}`); }
    }
    if (!falhas.length) { window.location.assign(salvo.url); return; }
    caixa.replaceChildren();
    const mensagem = document.createElement('p');
    mensagem.textContent = 'Seu registro está salvo. Algumas fotos não foram enviadas.';
    caixa.append(mensagem);
    falhas.forEach(falha => { const p = document.createElement('p'); p.textContent = falha; caixa.append(p); });
    const tentar = document.createElement('button');
    tentar.type = 'button'; tentar.className = 'botao secundario'; tentar.textContent = 'Tentar fotos novamente';
    tentar.addEventListener('click', () => enviarFotos(fotos, salvo));
    const continuar = document.createElement('a');
    continuar.href = salvo.url; continuar.textContent = 'Continuar com o registro salvo';
    caixa.append(tentar, continuar);
  }

  document.addEventListener('change', evento => {
    if (evento.target.matches('#categoria, input[name="nota"]')) atualizarFormulario();
    if (evento.target.matches('#fotos')) selecionarFotos(evento.target);
  });
  document.addEventListener('submit', async evento => {
    const form = evento.target;
    if (!form.matches('#cadastro, #anexar-fotos')) return;
    evento.preventDefault();
    if (form.dataset.enviando) return;
    const fotos = selecoes.get(form.querySelector('#fotos')) || [];
    if (form.id === 'anexar-fotos') {
      if (!fotos.length) { aviso('Escolha pelo menos uma foto.'); return; }
      form.hidden = true;
      await enviarFotos(fotos, {experiencia_id: form.dataset.experiencia, url: `/experiencias/${form.dataset.experiencia}`});
      return;
    }
    const dados = new URLSearchParams(new FormData(form));
    const acao = evento.submitter?.value || 'experiencia';
    if (acao === 'item' && fotos.length) { aviso('Para guardar fotos, escolha “Guardar experiência”.'); return; }
    dados.set('acao', acao);
    form.dataset.enviando = 'sim';
    form.querySelectorAll('button[type="submit"]').forEach(b => { b.disabled = true; });
    try {
      const salvo = await resposta(await fetch(form.action, {method: 'POST', body: dados,
        headers: {Accept: 'application/json'}, signal: AbortSignal.timeout(30000)}));
      if (!fotos.length) { window.location.assign(salvo.url); return; }
      form.hidden = true;
      document.querySelector('#erro-form').hidden = true;
      await enviarFotos(fotos, salvo);
    } catch (erro) {
      aviso(erro.message + ' Seus campos continuam preenchidos.');
    } finally {
      delete form.dataset.enviando;
      form.querySelectorAll('button[type="submit"]').forEach(b => { b.disabled = false; });
    }
  });
  document.addEventListener('DOMContentLoaded', atualizarFormulario);
  document.addEventListener('htmx:afterSwap', atualizarFormulario);
})();
