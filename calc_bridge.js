const { calculate, Pokemon, Move, Field } = require('@smogon/calc');

function runCalculation(input) {
  const gen = input.gen || 9;
  
  // Costruzione oggetti Smogon
  const attacker = new Pokemon(gen, input.attacker.name, input.attacker.options || {});
  const defender = new Pokemon(gen, input.defender.name, input.defender.options || {});
  const move = new Move(gen, input.move.name, input.move.options || {});
  const field = new Field(input.field || {});

  const result = calculate(gen, attacker, defender, move, field);

  return {
    damage: result.damage,
    minDamage: Array.isArray(result.damage) ? result.damage[0] : (typeof result.damage === 'number' ? result.damage : 0),
    maxDamage: Array.isArray(result.damage) ? result.damage[result.damage.length - 1] : (typeof result.damage === 'number' ? result.damage : 0),
    koChance: result.kochance ? (typeof result.kochance === 'function' ? result.kochance().text : result.kochance.text) : null,
    description: result.desc(),
    attackerSpe: attacker.stats ? attacker.stats.spe : 0,
    defenderSpe: defender.stats ? defender.stats.spe : 0,
    moveCategory: move.category
  };
}

// Interfaccia I/O via Stdin/Stdout per Python
let rawData = '';
process.stdin.on('data', chunk => { rawData += chunk; });
process.stdin.on('end', () => {
  try {
    const input = JSON.parse(rawData);
    if (Array.isArray(input)) {
        const output = input.map(item => {
            try {
                return { success: true, result: runCalculation(item) };
            } catch(e) {
                return { success: false, error: e.message };
            }
        });
        console.log(JSON.stringify(output));
    } else {
        const output = runCalculation(input);
        console.log(JSON.stringify(output));
    }
  } catch (err) {
    console.error(JSON.stringify({ error: err.message }));
    process.exit(1);
  }
});
