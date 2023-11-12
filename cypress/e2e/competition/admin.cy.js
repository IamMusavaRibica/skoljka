const UNLOCK_GRADUAL = 1;
const UNLOCK_ALL = 2;

/// Test that a chain with chainId exist (in the admin Problems page), and that
/// it contains the ctasks `ctaskIds`, in that exact order.
function checkChainTasks(chainId, ctaskIds) {
  return cy.get(`#chain-${chainId}`).then((tr) => {
    const ctaskTrs = [];
    for (let i = 0; i < ctaskIds.length; ++i) {
      tr = tr.next();
      ctaskTrs.push(tr);
      expect(tr.length).to.be.greaterThan(0);
      expect(tr).to.have.class('comp-tr-ctask');
      expect(tr).to.have.attr('data-id', ctaskIds[i].toString());
    }

    // No additional ctasks should be here.
    const next = tr.next();
    if (next.length) {
      expect(next).to.have.class('cchain-list');
    }
    return ctaskTrs;
  });
}

// TODO: Add view permission tests.
describe("test view permission", () => {
  before(() => {
    cy.resetdb();
    cy.request({ method: 'POST', url: '/competition/test/fill/' });
  });

  it("homepage should return 404 to non-moderators", () => {
    cy.login('alice');
    cy.expectForbidden('/hidden_competition/');
  });

  it("should display the competition homepage to moderators", () => {
    cy.login('moderator0');
    cy.visit('/hidden_competition/');
    cy.get('#sidebar').contains("moderator0"); // Hello, moderator0!
  });

});

describe("test adding a new task", () => {
  before(() => {
    cy.resetdb();
    cy.request({ method: 'POST', url: '/competition/test/fill/' });
  });

  beforeEach(() => {
    cy.login('moderator0');
    cy.setlang('en');
  });

  it("test the default values and the required fields", () => {
    cy.visit('/public_competition/task/new/');
    cy.get('textarea').should('have.length', 2); // Text + comment.
    cy.get('#content input').should('have.length', 3); // CSRF + descriptor + max_score.
    cy.get('#id_descriptor').should('have.value', "");
    cy.get('#id_max_score').should('have.value', "1");
    cy.get('#id_text').should('have.value', "");
    cy.get('#id_comment').should('have.value', "");

    cy.get('#id_descriptor').clear();
    cy.get('#id_max_score').clear();
    cy.get('#id_text').clear();
    cy.get('#id_comment').clear();
    cy.get('#id_descriptor').type('{enter}'); // Submit.

    cy.get('#id_descriptor').requiredFieldError();
    cy.get('#id_max_score').requiredFieldError();
    cy.get('#id_text').requiredFieldError();
  });

  it("test the add task form and the primary submit button", () => {
    cy.visit('/public_competition/task/new/');
    cy.get('#id_descriptor').type("123");
    cy.get('#id_max_score').clear().type("10");

    // Test the text preview.
    cy.get('#id_text').clear().type("What is 100 + 23?{ctrl+M}");
    cy.get('#form-ctask-text').contains("What is 100 + 23?");
    cy.get('#id_text').type(" Hello.");
    cy.get('button[data-source="id_text"]').click();
    cy.get('#form-ctask-text').contains("What is 100 + 23? Hello.");

    // Test the comment preview.
    cy.get('#id_comment').clear().type("A comment.{ctrl+M}");
    cy.get('#form-ctask-comment').contains("A comment.");
    cy.get('#id_comment').type(" Another comment.");
    cy.get('button[data-source="id_comment"]').click();
    cy.get('#form-ctask-comment').contains("A comment. Another comment.");

    // Test the primary submit button (save and stay).
    cy.get('[data-cy="submit-primary"]').contains("Submit");
    cy.get('[data-cy="submit-primary"]').click();
    cy.location('pathname').should('match', /^\/public_competition\/task\/\d+\/edit\/$/);
    cy.get('[data-cy="submit-primary"]').contains("Save changes");
    cy.get('#id_descriptor').should('have.value', "123");
    cy.get('#id_max_score').should('have.value', "10");
    cy.get('#id_text').should('have.value', "What is 100 + 23? Hello.");
    cy.get('#id_comment').should('have.value', "A comment. Another comment.");
    cy.get('[data-cy="go-to-problem"]').click(); // Go to the (non-admin) task detail page.
    cy.get('#content .mc').contains("What is 100 + 23? Hello.");
  });

  it("test adding a task with the submit-and-new button", () => {
    cy.visit('/public_competition/task/new/');
    cy.get('#id_descriptor').type("123");
    cy.get('#id_max_score').clear().type("10");
    cy.get('#id_text').clear().type("Text submit-and-new.");
    cy.get('#id_comment').clear().type("Comment submit-and-new.");
    cy.get('[data-cy="submit-and-new"]').click();
    cy.location('pathname').should('eq', '/public_competition/task/new/');
    cy.get('#id_descriptor').should('have.value', "");
    cy.get('#id_max_score').should('have.value', "1");
    cy.get('#id_text').should('have.value', "");
    cy.get('#id_comment').should('have.value', "");
    cy.visit('/public_competition/chain/tasks/');
    cy.get('#cchain-unused-ctasks-table tr:last-child').contains("Text submit-and-new.");
    cy.get('#cchain-unused-ctasks-table tr:last-child').contains("Comment submit-and-new.");
  });

  it("test adding a task with the submit-and-return button", () => {
    cy.visit('/public_competition/task/new/');
    cy.get('#id_descriptor').type("123");
    cy.get('#id_max_score').clear().type("10");
    cy.get('#id_text').clear().type("Text submit-and-return.");
    cy.get('#id_comment').clear().type("Comment submit-and-return.");
    cy.get('[data-cy="submit-and-return"]').click();
    cy.location('pathname').should('eq', '/public_competition/chain/tasks/');
    cy.get('#cchain-unused-ctasks-table tr:last-child').contains("Text submit-and-return.");
    cy.get('#cchain-unused-ctasks-table tr:last-child').contains("Comment submit-and-return.");
  });
});


describe("test adding and operating on chains", () => {
  before(() => {
    cy.resetdb();
    cy.request({ method: 'POST', url: '/competition/test/fill/' });
  });

  beforeEach(() => {
    cy.login('moderator0');
    cy.setlang('en');
  });

  it("test the default values and the required fields", () => {
    cy.visit('/public_competition/chain/tasks/');
    // CSRF + name + category + unlock minutes + bonus score + position +
    // hidden task_ids + submit + restricted access.
    cy.get('form[data-cy="create-chain"] input').should('have.length', 9);
    cy.get('form[data-cy="create-chain"] select').should('have.length', 1); // Unlock mode.
    cy.get('#id_name').should('have.value', "");
    cy.get('#id_category').should('have.value', "");
    cy.get('#id_unlock_minutes').should('have.value', "0");
    cy.get('#id_bonus_score').should('have.value', "1");
    cy.get('#id_position').should('have.value', "0");
    cy.get('#id_unlock_mode').should('have.value', "1");
    cy.get('#id_restricted_access').should('not.be.checked');

    cy.get('#id_unlock_minutes').clear();
    cy.get('#id_bonus_score').clear();
    cy.get('#id_position').clear();
    cy.get('form[data-cy="create-chain"] [type="submit"]').type('{enter}'); // Submit.

    cy.get('#id_name').requiredFieldError();
    cy.get('#id_unlock_minutes').requiredFieldError();
    cy.get('#id_bonus_score').requiredFieldError();
    cy.get('#id_position').requiredFieldError();
  });

  it("test creating and deleting an empty chain", () => {
    cy.visit('/public_competition/chain/tasks/');
    cy.get('#id_name').clear().type("empty test chain");
    cy.get('#id_category').clear().type("test category");
    cy.get('#id_unlock_minutes').clear().type("100");
    cy.get('#id_bonus_score').clear().type("1");
    cy.get('#id_position').clear().type("100");
    cy.get('#id_unlock_mode').select("2"); // All tasks unlocked.
    cy.get('input[data-cy="create-chain"]').click();
    cy.get('[data-cy="chain-created-successfully"]').should('exist');
    cy.get('#used-tasks-table a').contains("empty test chain").parents('.cchain-list').then((tr) => {
      expect(tr).to.have.class('cchain-verified-list'); // Empty chain is always verified.
      cy.wrap(tr).find('td').should('have.length', 6);
      cy.wrap(tr).find('td:nth-child(1)').contains("test category");
      cy.wrap(tr).find('td:nth-child(1)').contains("(position=100)");
      cy.wrap(tr).find('td:nth-child(2)').contains("empty test chain");
      cy.wrap(tr).find('td:nth-child(3)').contains("100 min.");
      cy.wrap(tr).find('td:nth-child(5)').contains("Edit chain");
      cy.wrap(tr).find('td:nth-child(6)').contains("Overview");
      cy.wrap(tr).find('td:nth-child(4)').find('button').click(); // Delete.
      cy.get('#used-tasks-table').contains("empty test chain").should('not.exist');
    });
  });

  it("test creating and deleting a chain with 4 tasks", () => {
    cy.createCTasks('public_competition', 4, "XYZW #{}", "task comment #{}").then((json) => {
      const ctask_ids = json.ctask_ids;
      cy.visit('/public_competition/chain/tasks/');

      // Select in some order, let's say 1302.
      cy.get('#cchain-unused-ctasks-table tr').contains("XYZW #1").click();
      cy.get('#cchain-unused-ctasks-table tr').contains("XYZW #3").click();
      cy.get('#cchain-unused-ctasks-table tr').contains("XYZW #0").click();
      cy.get('#cchain-unused-ctasks-table tr').contains("XYZW #2").click();
      cy.get('#id_name').clear().type("test 4-task chain");
      cy.get('input[data-cy="create-chain"]').click();
      cy.get('[data-cy="chain-created-successfully"]').should('exist');

      cy.get('#used-tasks-table a').contains("test 4-task chain").parents('.cchain-list').then((tr) => {
        expect(tr).to.not.have.class('cchain-verified-list'); // Tasks were not verified.

        cy.wrap(tr).as('ctask-tr');
        const expected_ids = [ctask_ids[1], ctask_ids[3], ctask_ids[0], ctask_ids[2]];
        for (const id of expected_ids) {
          cy.get('@ctask-tr').next().as('ctask-tr');
          cy.get('@ctask-tr').should('have.class', 'comp-tr-ctask');
          cy.get('@ctask-tr').invoke('attr', 'data-id').should('eq', id.toString());
        }

        // Delete chain and test that the tasks are now unused.
        cy.wrap(tr).find('button[data-cy="delete-chain"]').click();
        cy.get('#used-tasks-table a').contains("test 4-task chain").should('not.exist');
        for (const id of expected_ids) {
          cy.get(`#cchain-unused-ctasks-table tr.comp-tr-ctask[data-id="${id}"]`).should('exist');
        }
      });
    });
  });

  it("test changing the order of ctasks in a chain", () => {
    // Add some extra tasks to differentiate between indices and IDs, and to check
    // that the operations don't affect wrong tasks. Also, test cehckChainTasks itself.
    cy.createChain('public_competition', { numTasks: 3, position: 50, name: "unused chain A" });
    cy.createChain('public_competition', { numTasks: 3, position: 150, name: "unused chain B" });
    cy.createChain('public_competition', { numTasks: 4, position: 100 }).then((json) => {
      cy.visit('/public_competition/chain/tasks/');

      const chainId = json['chain_id'];
      const cids = json['ctask_ids'];
      checkChainTasks(chainId, cids).then((ctaskTrsA) => {
        cy.wrap(ctaskTrsA[1]).find('[data-cy="move-ctask-up"]').click();
        checkChainTasks(chainId, [cids[1], cids[0], cids[2], cids[3]]).then((ctaskTrsB) => {
          cy.wrap(ctaskTrsB[2]).find('[data-cy="move-ctask-down"]').click();
          checkChainTasks(chainId, [cids[1], cids[0], cids[3], cids[2]]);
        });
      });
    });
  });

  it("test detaching a task from a chain", () => {
    cy.createChain('public_competition', { numTasks: 4 }).then((json) => {
      cy.visit('/public_competition/chain/tasks/');

      const chainId = json['chain_id'];
      const cids = json['ctask_ids'];
      checkChainTasks(chainId, cids).then((ctaskTrsA) => {
        cy.wrap(ctaskTrsA[1]).find('[data-cy="detach-ctask"]').click();
        checkChainTasks(chainId, [cids[0], cids[2], cids[3]]).then((ctaskTrsB) => {
          cy.wrap(ctaskTrsB[2]).find('[data-cy="detach-ctask"]').click();
          checkChainTasks(chainId, [cids[0], cids[2]]);
        });
      });
    });
  });
});
