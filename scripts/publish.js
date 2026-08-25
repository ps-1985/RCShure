#!/usr/bin/env node

/**
 * RCShure - Git Quick Publish Script
 * Triggered via: npm run pub
 */

const { execSync } = require('child_process');
const readline = require('readline');

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout
});

console.log('\n========================================');
console.log('       RCShure - Git Quick Publish      ');
console.log('========================================\n');

try {
  // Check git status
  const status = execSync('git status --porcelain', { encoding: 'utf-8' }).trim();
  
  if (!status) {
    console.log('ℹ️  Nessuna modifica rilevata nel repository.');
    rl.close();
    process.exit(0);
  }

  console.log('Modifiche rilevate:');
  console.log(execSync('git status -s', { encoding: 'utf-8' }));

  rl.question('📝 Inserisci il messaggio di commit (INVIO per "Update: <timestamp>"): ', (answer) => {
    let commitMsg = answer.trim();
    
    if (!commitMsg) {
      const now = new Date();
      const pad = (n) => String(n).padStart(2, '0');
      const timestamp = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
      commitMsg = `Update: ${timestamp}`;
    }

    console.log(`\n⏳ 1/3 - Aggiunta modifiche (git add .)...`);
    execSync('git add .', { stdio: 'inherit' });

    console.log(`⏳ 2/3 - Creazione commit: "${commitMsg}"...`);
    execSync(`git commit -m "${commitMsg.replace(/"/g, '\\"')}"`, { stdio: 'inherit' });

    console.log(`⏳ 3/3 - Push su GitHub (git push)...`);
    execSync('git push', { stdio: 'inherit' });

    console.log('\n✅ Modifiche pubblicate con successo su GitHub!\n');
    rl.close();
  });
} catch (err) {
  console.error('\n❌ Errore durante la pubblicazione:', err.message || err);
  rl.close();
  process.exit(1);
}
