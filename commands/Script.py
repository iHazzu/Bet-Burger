import ast
import discord
from traceback import format_exception
from core import Context


def insert_returns(body):
    # insert return stmt if the last expression is a expression statement
    if isinstance(body[-1], ast.Expr):
        body[-1] = ast.Return(body[-1].value)
        ast.fix_missing_locations(body[-1])

    # for if statements, we insert returns into the body and the orelse
    if isinstance(body[-1], ast.If):
        insert_returns(body[-1].body)
        insert_returns(body[-1].orelse)

    # for with blocks, again we insert returns into the body
    if isinstance(body[-1], ast.With):
        insert_returns(body[-1].body)


def get_traceback(error: Exception) -> str:
    traceback = ''.join(format_exception(None, error, error.__traceback__))
    if len(traceback) > 2000:
        traceback = traceback[:2000] + '...'
    return traceback


async def go(ctx: Context, code: str):
    """Evaluates input.

    Input is interpreted as newline seperated statements.
    If the last statement is an expression, that is the return value.

    Such that `>eval 1 + 1` gives `2` as the result.

    The following invokation will cause the bot to send the text '9'
    to the channel of invokation and return '3' as the result of evaluating

    >eval ```
    a = 1 + 2
    b = a * 2
    await ctx.reply(a + b)
    ```
    """
    fn_name = "_eval_expr"
    code = code.strip("` ")
    lines = code.splitlines()
    if lines[0] == 'py':
        lines = lines[1:]

    # add a layer of indentation
    cmd = "\n".join(f"    {i}" for i in lines)

    # wrap in async def body
    body = f"async def {fn_name}():\n{cmd}"

    parsed = ast.parse(body)
    body = parsed.body[0].body

    insert_returns(body)

    env = {
        'ctx': ctx,
        'discord': discord,
        '__import__': __import__
    }
    try:
        exec(compile(parsed, filename="<ast>", mode="exec"), env)
        result = (await eval(f"{fn_name}()", env))
    except Exception as error:
        traceback = get_traceback(error)
        emb = discord.Embed(
            title="OCORREU UM ERRO",
            description=f"```\n{traceback}```",
            colour=16711680
        )
        emb.set_author(name=f'Solicitado por {ctx.author}', icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=emb)
    else:
        if not result or isinstance(result, discord.Message):
            result = '• Sem Retorno'
        await ctx.send(f'🤖 {ctx.author.mention} **|** Script executado!```prolog\n{result}```')